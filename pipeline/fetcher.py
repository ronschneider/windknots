"""Fetch content from RSS feeds, NewsAPI, and Reddit."""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


# Keywords that indicate fly fishing content
FISHING_KEYWORDS = [
    # Fly fishing specific
    r'\bfly fishing', r'\bfly-fishing', r'\bflyfishing', r'\bfly rod', r'\bfly reel',
    r'\bfly line', r'\bfly tying', r'\bfly tier', r'\btying flies', r'\btied flies',
    r'\bnymph\b', r'\bdry fly', r'\bstreamer', r'\bemerger', r'\bwet fly',
    r'\bmayfly', r'\bcaddis', r'\bstonefly', r'\bmidge', r'\bhopper', r'\bterrestrial',
    r'\bspey\b', r'\beuro nymph', r'\btightline', r'\bswing\b.*fly', r'\bstrip\b.*fly',
    r'\bwader', r'\bwading\b', r'\bbackcast', r'\broll cast', r'\bfalse cast',
    r'\btippet', r'\bleader\b', r'\bfloatant', r'\bindicator', r'\bstrike indicator',
    r'\bwooly bugger', r'\badams\b', r'\belk hair', r'\bpheasant tail', r'\bprince nymph',
    r'\bparachute\b.*fly', r'\bcomparadun', r'\bstimulator', r'\bmuddler',
    # Target species (fly fishing focused)
    r'\btrout\b', r'\bsalmon\b', r'\bsteelhead', r'\bbonefish', r'\btarpon', r'\bpermit\b(?!s)',
    r'\bcarp\b.*fly', r'\bbass\b.*fly', r'\bbrookie', r'\bbrook trout', r'\bbrown trout',
    r'\brainbow\b', r'\bcutthroat', r'\bgolden trout', r'\bgrayling', r'\bchar\b',
    # General that often relates to fly fishing
    r'\bhatch\b', r'\brising\b.*fish', r'\brise\b.*form', r'\bmatch the hatch',
    r'\bdrift\b.*fly', r'\bdead drift', r'\bswung fly', r'\bstrip set',
]

# Keywords that indicate non-fly-fishing content
EXCLUDE_KEYWORDS = [
    # Hunting
    r'\bhunt\b', r'\bhunter', r'\bhunting\b', r'\bdeer\b', r'\belk\b(?!.*hair)', r'\bmoose\b',
    r'\bbear\b(?! bait)', r'\bturkey\b(?! fish)', r'\bduck\b(?! decoy)', r'\bgoose\b',
    r'\bpheasant(?!.*tail)', r'\bquail\b', r'\bdove\b', r'\bwaterfowl', r'\bupland',
    r'\brifle\b', r'\bshotgun', r'\bammunition', r'\bammo\b', r'\bcartridge',
    r'\bballistic', r'\bscope\b(?! fish)', r'\bbinocular', r'\bglassing',
    r'\bbow\b(?! fish)', r'\barchery', r'\bcrossbow', r'\btreestand', r'\bblind\b',
    r'\bdecoy\b(?! fish)', r'\bgame camera', r'\btrail cam',
    r'\bbison\b', r'\bwolf\b', r'\bwolves\b', r'\bpredator(?! fish)',
    # Conventional fishing (not fly)
    r'\bbaitcast', r'\bspinning reel', r'\btrolling\b', r'\bjig\b(?!.*fly)',
    r'\bcrankbait', r'\bspinnerbait', r'\bbass boat', r'\btournament bass',
]

# Compiled patterns for efficiency
_FISHING_PATTERNS = [re.compile(kw, re.IGNORECASE) for kw in FISHING_KEYWORDS]
_EXCLUDE_PATTERNS = [re.compile(kw, re.IGNORECASE) for kw in EXCLUDE_KEYWORDS]


def is_fishing_content(title: str, description: str) -> bool:
    """Check if content is fishing-related and not primarily hunting/other.

    Args:
        title: Article title
        description: Article description

    Returns:
        True if the content is fishing-related
    """
    text = f"{title} {description}".lower()

    # Count fishing keyword matches
    fishing_score = sum(1 for p in _FISHING_PATTERNS if p.search(text))

    # Count exclude keyword matches
    exclude_score = sum(1 for p in _EXCLUDE_PATTERNS if p.search(text))

    # Article is fishing content if:
    # 1. Has at least one fishing keyword, AND
    # 2. Fishing keywords outnumber exclude keywords (or no excludes)
    return fishing_score > 0 and fishing_score >= exclude_score


@dataclass
class Article:
    """Raw article data from any source."""
    title: str
    url: str
    source_name: str
    published: datetime
    description: str
    image_url: Optional[str] = None
    author: Optional[str] = None


def load_sources() -> dict:
    """Load source configuration from data/sources.json."""
    sources_path = Path(__file__).parent.parent / "data" / "sources.json"
    with open(sources_path) as f:
        return json.load(f)


def load_seen_urls() -> set:
    """Load previously seen URLs for deduplication."""
    seen_path = Path(__file__).parent.parent / "data" / "seen_urls.json"
    if seen_path.exists():
        with open(seen_path) as f:
            return set(json.load(f))
    return set()


def save_seen_urls(urls: set) -> None:
    """Save seen URLs to disk."""
    seen_path = Path(__file__).parent.parent / "data" / "seen_urls.json"
    # Keep only last 5000 URLs to prevent unbounded growth
    urls_list = list(urls)[-5000:]
    with open(seen_path, "w") as f:
        json.dump(urls_list, f, indent=2)


def fetch_rss_feeds(sources: dict) -> list[Article]:
    """Fetch articles from configured RSS feeds."""
    articles = []

    for feed_config in sources.get("rss_feeds", []):
        if not feed_config.get("enabled", True):
            continue

        try:
            feed = feedparser.parse(feed_config["url"])

            for entry in feed.entries[:10]:  # Limit per feed
                # Parse date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])
                else:
                    published = datetime.now()

                # Extract image from media content or enclosures
                image_url = None
                if hasattr(entry, "media_content") and entry.media_content:
                    for media in entry.media_content:
                        if media.get("medium") == "image" or media.get("type", "").startswith("image"):
                            image_url = media.get("url")
                            break
                if not image_url and hasattr(entry, "enclosures"):
                    for enc in entry.enclosures:
                        if enc.get("type", "").startswith("image"):
                            image_url = enc.get("href") or enc.get("url")
                            break

                # Get description
                description = ""
                if hasattr(entry, "summary"):
                    description = entry.summary
                elif hasattr(entry, "description"):
                    description = entry.description

                articles.append(Article(
                    title=entry.title,
                    url=entry.link,
                    source_name=feed_config["name"],
                    published=published,
                    description=description,
                    image_url=image_url,
                    author=getattr(entry, "author", None)
                ))

        except Exception as e:
            print(f"Error fetching {feed_config['name']}: {e}")
            continue

    return articles


def fetch_newsapi(sources: dict) -> list[Article]:
    """Fetch articles from NewsAPI."""
    newsapi_config = sources.get("newsapi", {})
    if not newsapi_config.get("enabled", False):
        return []

    api_key = os.environ.get("NEWS_API_KEY")
    if not api_key:
        print("NEWS_API_KEY not set, skipping NewsAPI")
        return []

    articles = []

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": newsapi_config.get("query", "fishing"),
                    "language": newsapi_config.get("language", "en"),
                    "sortBy": newsapi_config.get("sort_by", "publishedAt"),
                    "pageSize": newsapi_config.get("page_size", 20),
                    "apiKey": api_key
                }
            )
            response.raise_for_status()
            data = response.json()

            for item in data.get("articles", []):
                published = datetime.now()
                if item.get("publishedAt"):
                    try:
                        published = date_parser.parse(item["publishedAt"])
                        published = published.replace(tzinfo=None)
                    except:
                        pass

                articles.append(Article(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    source_name=item.get("source", {}).get("name", "News"),
                    published=published,
                    description=item.get("description", ""),
                    image_url=item.get("urlToImage"),
                    author=item.get("author")
                ))

    except Exception as e:
        print(f"Error fetching NewsAPI: {e}")

    return articles


def fetch_reddit(sources: dict) -> list[Article]:
    """Fetch posts from Reddit via RSS feeds.

    Uses RSS since Reddit's JSON API now blocks unauthenticated requests.
    """
    reddit_config = sources.get("reddit", {})
    if not reddit_config.get("enabled", False):
        return []

    articles = []
    sort = reddit_config.get("sort", "hot")
    limit = reddit_config.get("limit", 10)

    for subreddit in reddit_config.get("subreddits", []):
        try:
            feed = feedparser.parse(
                f"https://www.reddit.com/r/{subreddit}/{sort}.rss?limit={limit}"
            )

            for entry in feed.entries:
                # Skip stickied/mod posts
                if entry.title.startswith("[MOD POST"):
                    continue

                # Parse published date
                published = datetime.now()
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])

                # Extract image URL from HTML content
                image_url = None
                html = entry.content[0].value if hasattr(entry, "content") else ""
                if html:
                    soup = BeautifulSoup(html, "html.parser")
                    img = soup.select_one("img")
                    if img and img.get("src"):
                        image_url = img["src"]

                    # Extract text description from self-posts
                    md_div = soup.select_one("div.md")
                    description = md_div.get_text(strip=True)[:500] if md_div else ""
                else:
                    description = ""

                articles.append(Article(
                    title=entry.title,
                    url=entry.link,
                    source_name=f"Reddit r/{subreddit}",
                    published=published,
                    description=description,
                    image_url=image_url,
                    author=getattr(entry, "author", "").replace("/u/", "") or None,
                ))

        except Exception as e:
            print(f"Error fetching r/{subreddit}: {e}")
            continue

    return articles


def fetch_all_content() -> list[Article]:
    """Fetch content from all configured sources, deduplicated and filtered."""
    sources = load_sources()
    seen_urls = load_seen_urls()

    all_articles = []

    # Fetch from all sources
    all_articles.extend(fetch_rss_feeds(sources))
    all_articles.extend(fetch_newsapi(sources))
    all_articles.extend(fetch_reddit(sources))

    # Deduplicate and filter to fishing content only
    new_articles = []
    filtered_count = 0
    for article in all_articles:
        if article.url and article.url not in seen_urls:
            # Filter to fishing content only
            if is_fishing_content(article.title, article.description):
                new_articles.append(article)
                seen_urls.add(article.url)
            else:
                filtered_count += 1

    # Save updated seen URLs
    save_seen_urls(seen_urls)

    # Sort by publish date (newest first)
    new_articles.sort(key=lambda a: a.published, reverse=True)

    print(f"Fetched {len(new_articles)} fishing articles ({filtered_count} non-fishing filtered out, from {len(all_articles)} total)")

    return new_articles


if __name__ == "__main__":
    articles = fetch_all_content()
    for article in articles[:5]:
        print(f"- {article.title} ({article.source_name})")

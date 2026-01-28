"""Fetch weblinks for daily digest: Reddit discussions, gear deals, new trips."""

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup


@dataclass
class RedditDiscussion:
    """A Reddit self-post discussion."""
    title: str
    url: str
    subreddit: str
    upvotes: int
    comment_count: int
    author: str


@dataclass
class GearDeal:
    """A gear deal from a retailer."""
    title: str
    url: str
    source: str
    original_price: Optional[str] = None
    sale_price: Optional[str] = None
    discount: Optional[str] = None


@dataclass
class Trip:
    """A fishing trip/destination from an outfitter."""
    title: str
    url: str
    destination: str
    source: str
    description: Optional[str] = None


def load_sources() -> dict:
    """Load source configuration from data/sources.json."""
    sources_path = Path(__file__).parent.parent / "data" / "sources.json"
    with open(sources_path) as f:
        return json.load(f)


def fetch_reddit_discussions(limit: int = 10) -> list[RedditDiscussion]:
    """Fetch hot self-posts (discussions) from fly fishing subreddits.

    Args:
        limit: Maximum number of discussions to return

    Returns:
        List of RedditDiscussion objects
    """
    sources = load_sources()
    reddit_config = sources.get("reddit", {})

    if not reddit_config.get("enabled", False):
        return []

    discussions = []
    headers = {
        "User-Agent": "Windknots/1.0 (fishing content aggregator)"
    }

    subreddits = reddit_config.get("subreddits", ["flyfishing", "flytying"])

    for subreddit in subreddits:
        try:
            with httpx.Client(timeout=30, headers=headers) as client:
                url = f"https://www.reddit.com/r/{subreddit}/hot.json"
                response = client.get(url, params={"limit": 25})
                response.raise_for_status()
                data = response.json()

                for post in data.get("data", {}).get("children", []):
                    post_data = post.get("data", {})

                    # Only include self-posts (discussions)
                    if not post_data.get("is_self") or post_data.get("stickied"):
                        continue

                    # Skip low-engagement posts
                    if post_data.get("score", 0) < 10:
                        continue

                    discussions.append(RedditDiscussion(
                        title=post_data.get("title", ""),
                        url=f"https://reddit.com{post_data.get('permalink', '')}",
                        subreddit=f"r/{subreddit}",
                        upvotes=post_data.get("score", 0),
                        comment_count=post_data.get("num_comments", 0),
                        author=post_data.get("author", "")
                    ))

        except Exception as e:
            print(f"Error fetching r/{subreddit} discussions: {e}")
            continue

    # Sort by upvotes and limit
    discussions.sort(key=lambda d: d.upvotes, reverse=True)
    return discussions[:limit]


def fetch_orvis_deals(limit: int = 5) -> list[GearDeal]:
    """Scrape current deals from Orvis sale page.

    Args:
        limit: Maximum number of deals to return

    Returns:
        List of GearDeal objects
    """
    deals = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
            # Try the fly fishing sale page
            response = client.get("https://www.orvis.com/fly-fishing-sale")
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Find product cards - Orvis uses various selectors
            products = soup.select(".product-tile, .product-card, [data-component='ProductTile']")

            for product in products[:limit * 2]:  # Get extra to filter
                try:
                    # Try various selectors for product data
                    title_el = product.select_one(".product-name, .product-title, h3, h2")
                    link_el = product.select_one("a[href*='/p/']")
                    price_els = product.select(".price, .product-price span")

                    if not title_el or not link_el:
                        continue

                    title = title_el.get_text(strip=True)
                    url = link_el.get("href", "")
                    if not url.startswith("http"):
                        url = f"https://www.orvis.com{url}"

                    # Extract prices if available
                    original_price = None
                    sale_price = None
                    for price_el in price_els:
                        price_text = price_el.get_text(strip=True)
                        if "was" in price_el.get("class", []) or "original" in str(price_el.get("class", [])):
                            original_price = price_text
                        elif "$" in price_text:
                            sale_price = price_text

                    deals.append(GearDeal(
                        title=title,
                        url=url,
                        source="Orvis",
                        original_price=original_price,
                        sale_price=sale_price
                    ))

                except Exception:
                    continue

    except Exception as e:
        print(f"Error fetching Orvis deals: {e}")

    return deals[:limit]


def fetch_simms_deals(limit: int = 5) -> list[GearDeal]:
    """Scrape current deals from Simms sale page.

    Args:
        limit: Maximum number of deals to return

    Returns:
        List of GearDeal objects
    """
    deals = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
            response = client.get("https://www.simmsfishing.com/sale")
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Find product elements
            products = soup.select(".product-item, .product-card, .product-tile")

            for product in products[:limit * 2]:
                try:
                    title_el = product.select_one(".product-item-name, .product-name, h3, h2")
                    link_el = product.select_one("a[href*='simmsfishing.com']") or product.select_one("a")

                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    url = ""
                    if link_el:
                        url = link_el.get("href", "")
                        if not url.startswith("http"):
                            url = f"https://www.simmsfishing.com{url}"

                    # Look for price elements
                    original_el = product.select_one(".old-price, .was-price, .original-price")
                    sale_el = product.select_one(".special-price, .sale-price, .current-price")

                    original_price = original_el.get_text(strip=True) if original_el else None
                    sale_price = sale_el.get_text(strip=True) if sale_el else None

                    deals.append(GearDeal(
                        title=title,
                        url=url,
                        source="Simms",
                        original_price=original_price,
                        sale_price=sale_price
                    ))

                except Exception:
                    continue

    except Exception as e:
        print(f"Error fetching Simms deals: {e}")

    return deals[:limit]


def fetch_yellowdog_trips(limit: int = 5) -> list[Trip]:
    """Scrape featured trips from Yellow Dog Flyfishing Adventures.

    Args:
        limit: Maximum number of trips to return

    Returns:
        List of Trip objects
    """
    trips = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
            response = client.get("https://www.yellowdogflyfishing.com/destinations")
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Find destination/trip cards
            destinations = soup.select(".destination-card, .trip-card, .lodge-card, article")

            for dest in destinations[:limit * 2]:
                try:
                    title_el = dest.select_one("h2, h3, .title, .destination-name")
                    link_el = dest.select_one("a[href*='yellowdog']") or dest.select_one("a")
                    desc_el = dest.select_one("p, .description, .excerpt")
                    location_el = dest.select_one(".location, .country, .region")

                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    url = ""
                    if link_el:
                        url = link_el.get("href", "")
                        if not url.startswith("http"):
                            url = f"https://www.yellowdogflyfishing.com{url}"

                    destination = ""
                    if location_el:
                        destination = location_el.get_text(strip=True)
                    else:
                        # Try to extract destination from title
                        match = re.search(r'(?:in|to)\s+([A-Z][a-zA-Z\s]+)', title)
                        if match:
                            destination = match.group(1).strip()

                    description = desc_el.get_text(strip=True)[:200] if desc_el else None

                    trips.append(Trip(
                        title=title,
                        url=url,
                        destination=destination,
                        source="Yellow Dog",
                        description=description
                    ))

                except Exception:
                    continue

    except Exception as e:
        print(f"Error fetching Yellow Dog trips: {e}")

    return trips[:limit]


def fetch_all_weblinks() -> dict:
    """Fetch all weblinks for the daily digest.

    Returns:
        Dictionary with reddit, deals, and trips lists
    """
    print("Fetching weblinks...")

    print("  - Reddit discussions...")
    reddit = fetch_reddit_discussions(limit=8)
    print(f"    Found {len(reddit)} discussions")

    print("  - Orvis deals...")
    orvis_deals = fetch_orvis_deals(limit=5)
    print(f"    Found {len(orvis_deals)} Orvis deals")

    print("  - Simms deals...")
    simms_deals = fetch_simms_deals(limit=5)
    print(f"    Found {len(simms_deals)} Simms deals")

    print("  - Yellow Dog trips...")
    trips = fetch_yellowdog_trips(limit=5)
    print(f"    Found {len(trips)} trips")

    # Combine deals
    all_deals = orvis_deals + simms_deals

    return {
        "reddit": [asdict(r) for r in reddit],
        "deals": [asdict(d) for d in all_deals],
        "trips": [asdict(t) for t in trips]
    }


if __name__ == "__main__":
    weblinks = fetch_all_weblinks()
    print("\n=== Reddit Discussions ===")
    for r in weblinks["reddit"][:3]:
        print(f"  [{r['upvotes']}] {r['title'][:50]}...")
    print(f"\n=== Deals ({len(weblinks['deals'])}) ===")
    for d in weblinks["deals"][:3]:
        print(f"  [{d['source']}] {d['title'][:50]}...")
    print(f"\n=== Trips ({len(weblinks['trips'])}) ===")
    for t in weblinks["trips"][:3]:
        print(f"  [{t['destination']}] {t['title'][:50]}...")

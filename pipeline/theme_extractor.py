"""AI-powered theme extraction for cross-article analysis."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class Theme:
    """A theme identified across multiple articles."""
    title: str
    slug: str
    description: str
    editorial_intro: str
    article_ids: list[str]  # List of article filenames
    tags: list[str]
    image_path: str  # Path to generated image
    created: datetime


@dataclass
class ArticleData:
    """Simplified article data for theme analysis."""
    filename: str
    title: str
    summary: str
    tags: list[str]
    source_name: str
    date: datetime


def get_openai_client() -> Optional[OpenAI]:
    """Get OpenAI client if API key is available."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def load_recent_articles(days: int = 7) -> list[ArticleData]:
    """Load recent articles from the content directory.

    Args:
        days: Number of days to look back

    Returns:
        List of ArticleData objects
    """
    content_dir = Path(__file__).parent.parent / "content" / "articles"
    articles = []

    if not content_dir.exists():
        return articles

    for md_file in content_dir.glob("*.md"):
        if md_file.name == "_index.md":
            continue

        try:
            content = md_file.read_text(encoding="utf-8")

            # Parse frontmatter (simple YAML parsing)
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]

                    # Extract fields
                    title = ""
                    summary = ""
                    tags = []
                    source_name = ""
                    date_str = ""

                    for line in frontmatter.strip().split("\n"):
                        if line.startswith("title:"):
                            title = line.split(":", 1)[1].strip().strip('"')
                        elif line.startswith("summary:"):
                            summary = line.split(":", 1)[1].strip().strip('"')
                        elif line.startswith("source_name:"):
                            source_name = line.split(":", 1)[1].strip().strip('"')
                        elif line.startswith("date:"):
                            date_str = line.split(":", 1)[1].strip()
                        elif line.strip().startswith('- "'):
                            tag = line.strip()[3:-1]  # Remove '- "' and '"'
                            tags.append(tag)

                    # Parse date
                    article_date = datetime.now()
                    if date_str:
                        try:
                            article_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        except:
                            pass

                    articles.append(ArticleData(
                        filename=md_file.name,
                        title=title,
                        summary=summary,
                        tags=tags,
                        source_name=source_name,
                        date=article_date
                    ))

        except Exception as e:
            print(f"Error loading {md_file.name}: {e}")
            continue

    # Sort by date, newest first
    articles.sort(key=lambda a: a.date, reverse=True)

    return articles


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def identify_themes(articles: list[ArticleData], min_articles: int = 3) -> list[dict]:
    """Use AI to identify themes across a set of articles.

    Args:
        articles: List of articles to analyze
        min_articles: Minimum articles needed to form a theme

    Returns:
        List of theme dicts with title, description, and article_indices
    """
    client = get_openai_client()

    if not client or len(articles) < min_articles:
        return []

    # Build article list for AI
    article_list = "\n".join(
        f"{i}. [{a.source_name}] {a.title}\n   Tags: {', '.join(a.tags)}\n   Summary: {a.summary[:150]}..."
        for i, a in enumerate(articles)
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are an editor for Windknots Daily Digest, a fly fishing content aggregator. Analyze articles to identify compelling fly fishing themes.

Look for:
1. Species-focused content (trout tactics, steelhead runs, saltwater flats)
2. Technique themes (dry fly fishing, nymphing, streamer strategies, spey casting)
3. Seasonal patterns (spring hatches, fall runs, winter fishing)
4. Fly tying patterns and tutorials
5. Gear and equipment (rods, reels, lines, waders)
6. Destination/travel features
7. Conservation and wild fish issues
8. Beginner and learning content

Return JSON with this format:
{
  "themes": [
    {
      "title": "Theme Title (catchy, fly-fishing editorial)",
      "description": "One sentence description of the theme",
      "article_indices": [0, 3, 5],
      "tags": ["relevant", "tags"],
      "quality_score": 8
    }
  ]
}

Rules:
- Only identify themes with 2+ articles (prefer 3+)
- Themes should be specific to fly fishing, not generic
- Generate 2-5 themes based on content quality
- Include a quality_score (1-10) for each theme
- Only include themes with quality_score >= 6
- Prefer themes that offer insights for fly anglers"""
                },
                {
                    "role": "user",
                    "content": f"Find themes in these {len(articles)} recent fishing articles:\n\n{article_list}"
                }
            ],
            max_tokens=800,
            temperature=0.5,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        themes = result.get("themes", [])

        # Filter by quality score if present
        themes = [t for t in themes if t.get("quality_score", 7) >= 6]

        # Limit to 5 max
        return themes[:5]

    except Exception as e:
        print(f"Error identifying themes: {e}")
        return []


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def generate_theme_content(theme_title: str, theme_desc: str, articles: list[ArticleData]) -> dict:
    """Generate editorial content for a theme.

    Args:
        theme_title: Title of the theme
        theme_desc: Brief description
        articles: Articles in this theme

    Returns:
        Dict with editorial_intro, enhanced_title, and takeaways
    """
    client = get_openai_client()

    if not client:
        return {
            "editorial_intro": theme_desc,
            "enhanced_title": theme_title,
            "takeaways": []
        }

    article_details = "\n\n".join(
        f"**{a.title}** ({a.source_name})\n{a.summary}"
        for a in articles
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are the editor of Windknots, a fishing content aggregator. Write editorial content
that synthesizes insights from multiple articles on a theme.

Return JSON with:
{
  "enhanced_title": "Punchy, editorial headline for this theme roundup",
  "editorial_intro": "2-3 paragraph editorial introduction that ties the articles together, offers insights, and gives anglers actionable takeaways. Write in first-person plural (we, our). Be conversational but authoritative.",
  "takeaways": ["Key takeaway 1", "Key takeaway 2", "Key takeaway 3"]
}

Style:
- Write like a seasoned fishing editor, not a content mill
- Draw connections the reader might miss
- Include specific, actionable insights
- Reference specific articles naturally
- Be opinionated where appropriate"""
                },
                {
                    "role": "user",
                    "content": f"Theme: {theme_title}\nDescription: {theme_desc}\n\nArticles:\n{article_details}"
                }
            ],
            max_tokens=600,
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"Error generating theme content: {e}")
        return {
            "editorial_intro": theme_desc,
            "enhanced_title": theme_title,
            "takeaways": []
        }


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def generate_theme_image(theme_title: str, theme_desc: str, tags: list[str]) -> str:
    """Generate an image for the theme using DALL-E.

    Args:
        theme_title: Title of the theme
        theme_desc: Description of the theme
        tags: Theme tags for context

    Returns:
        Relative path to saved image, or placeholder path
    """
    client = get_openai_client()

    if not client:
        return "/images/placeholder.jpg"

    # Create a fishing-focused image prompt
    tag_context = ", ".join(tags[:3]) if tags else "fishing"

    try:
        # Generate prompt for DALL-E
        prompt_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Create a DALL-E image prompt for a fishing article header image.
The image should be:
- Photorealistic or artistic illustration style
- Evocative of the fishing theme
- Suitable as a website header (landscape orientation)
- No text or words in the image
- Warm, inviting colors

Return ONLY the prompt, nothing else. Keep it under 200 characters."""
                },
                {
                    "role": "user",
                    "content": f"Theme: {theme_title}\nDescription: {theme_desc}\nTags: {tag_context}"
                }
            ],
            max_tokens=100,
            temperature=0.8
        )

        image_prompt = prompt_response.choices[0].message.content.strip()
        print(f"  Image prompt: {image_prompt[:60]}...")

        # Generate image with DALL-E
        image_response = client.images.generate(
            model="dall-e-3",
            prompt=image_prompt,
            size="1792x1024",  # Landscape for header
            quality="standard",
            n=1
        )

        image_url = image_response.data[0].url

        # Download and save image
        static_dir = Path(__file__).parent.parent / "static" / "images" / "themes"
        static_dir.mkdir(parents=True, exist_ok=True)

        # Create unique filename from theme title
        slug = theme_title.lower()
        slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
        slug = "-".join(slug.split())[:30]
        hash_suffix = hashlib.md5(theme_title.encode()).hexdigest()[:8]
        filename = f"{slug}-{hash_suffix}.png"

        # Download image
        with httpx.Client(timeout=60) as http_client:
            response = http_client.get(image_url)
            response.raise_for_status()

            file_path = static_dir / filename
            file_path.write_bytes(response.content)

        print(f"  Generated image: {filename}")
        return f"/images/themes/{filename}"

    except Exception as e:
        print(f"  Error generating image: {e}")
        return "/images/placeholder.jpg"


def create_theme_post(theme_data: dict, articles: list[ArticleData]) -> Theme:
    """Create a full theme post from identified theme and articles.

    Args:
        theme_data: Theme dict from identify_themes
        articles: Full list of articles

    Returns:
        Theme object ready to be saved
    """
    # Get articles for this theme
    theme_articles = [articles[i] for i in theme_data["article_indices"] if i < len(articles)]

    # Generate editorial content
    content = generate_theme_content(
        theme_data["title"],
        theme_data["description"],
        theme_articles
    )

    enhanced_title = content.get("enhanced_title", theme_data["title"])

    # Generate image for the theme
    print("  Generating header image...")
    image_path = generate_theme_image(
        enhanced_title,
        theme_data["description"],
        theme_data.get("tags", [])
    )

    # Create slug
    slug = theme_data["title"].lower()
    slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
    slug = "-".join(slug.split())[:50]

    return Theme(
        title=enhanced_title,
        slug=slug,
        description=theme_data["description"],
        editorial_intro=content.get("editorial_intro", theme_data["description"]),
        article_ids=[a.filename for a in theme_articles],
        tags=theme_data.get("tags", []),
        image_path=image_path,
        created=datetime.now()
    )


def save_theme_post(theme: Theme) -> Path:
    """Save a theme as a Hugo markdown file.

    Args:
        theme: Theme object to save

    Returns:
        Path to saved file
    """
    content_dir = Path(__file__).parent.parent / "content" / "themes"
    content_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = theme.created.strftime("%Y-%m-%d")
    filename = f"{date_prefix}-{theme.slug}.md"

    # Format tags
    tags_yaml = "\n".join(f'  - "{tag}"' for tag in theme.tags)

    # Format related articles
    articles_yaml = "\n".join(f'  - "{aid}"' for aid in theme.article_ids)

    markdown = f'''---
title: "{theme.title}"
date: {theme.created.strftime("%Y-%m-%dT%H:%M:%SZ")}
type: "theme"
description: "{theme.description}"
image: "{theme.image_path}"
tags:
{tags_yaml}
related_articles:
{articles_yaml}
---

{theme.editorial_intro}

## Related Articles

{{{{< theme-articles >}}}}
'''

    file_path = content_dir / filename
    file_path.write_text(markdown, encoding="utf-8")

    return file_path


def extract_themes_data(min_articles: int = 3, days: int = 14) -> list[dict]:
    """Extract themes and return as structured data (for digest generation).

    Args:
        min_articles: Minimum articles needed per theme
        days: Number of days to look back for articles

    Returns:
        List of theme dicts with all data needed for digest
    """
    print("Loading recent articles...")
    articles = load_recent_articles(days=days)
    print(f"Found {len(articles)} articles")

    if len(articles) < min_articles:
        print("Not enough articles for theme extraction")
        return []

    print("Identifying themes with AI...")
    themes = identify_themes(articles, min_articles)
    print(f"Found {len(themes)} potential themes")

    theme_data_list = []
    for theme_info in themes:
        print(f"\nProcessing theme: {theme_info['title']}")

        # Get articles for this theme
        theme_articles = [articles[i] for i in theme_info["article_indices"] if i < len(articles)]

        # Generate editorial content
        content = generate_theme_content(
            theme_info["title"],
            theme_info["description"],
            theme_articles
        )

        enhanced_title = content.get("enhanced_title", theme_info["title"])

        # Generate image for the theme
        print("  Generating header image...")
        image_path = generate_theme_image(
            enhanced_title,
            theme_info["description"],
            theme_info.get("tags", [])
        )

        # Build article data for digest
        article_data = []
        for a in theme_articles:
            article_data.append({
                "filename": a.filename,
                "title": a.title,
                "source_name": a.source_name,
                "summary": a.summary[:200] if a.summary else ""
            })

        theme_data_list.append({
            "title": enhanced_title,
            "description": theme_info["description"],
            "editorial_intro": content.get("editorial_intro", theme_info["description"]),
            "image": image_path,
            "tags": theme_info.get("tags", []),
            "articles": article_data,
            "takeaways": content.get("takeaways", [])
        })

        print(f"  -> Processed: {enhanced_title}")

    return theme_data_list


def extract_and_save_themes(min_articles: int = 3) -> list[Path]:
    """Main entry point: analyze recent articles and create theme posts.

    Args:
        min_articles: Minimum articles needed per theme

    Returns:
        List of paths to created theme files
    """
    print("Loading recent articles...")
    articles = load_recent_articles(days=14)
    print(f"Found {len(articles)} articles")

    if len(articles) < min_articles:
        print("Not enough articles for theme extraction")
        return []

    print("Identifying themes with AI...")
    themes = identify_themes(articles, min_articles)
    print(f"Found {len(themes)} potential themes")

    created_files = []
    for theme_data in themes:
        print(f"\nProcessing theme: {theme_data['title']}")
        theme = create_theme_post(theme_data, articles)
        file_path = save_theme_post(theme)
        created_files.append(file_path)
        print(f"  -> Saved: {file_path.name}")

    return created_files


if __name__ == "__main__":
    files = extract_and_save_themes()
    print(f"\nCreated {len(files)} theme posts")

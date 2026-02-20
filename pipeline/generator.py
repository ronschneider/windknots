"""Generate Hugo markdown files from processed articles."""

import argparse
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .fetcher import Article, fetch_all_content
from .summarizer import summarize_article, clean_description
from .tagger import auto_tag
from .image_extractor import process_article_image, create_placeholder_image
from .theme_extractor import extract_and_save_themes
from .digest_generator import generate_daily_digest


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    slug = text.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug[:60]


def generate_markdown(
    title: str,
    date: datetime,
    source_url: str,
    source_name: str,
    summary: str,
    image_path: str,
    tags: list[str],
    author: Optional[str] = None
) -> str:
    """Generate Hugo-compatible markdown content."""
    # Escape for YAML
    safe_title = title.replace('"', '\\"').replace('\n', ' ').strip()
    safe_summary = summary.replace('"', '\\"').replace('\n', ' ').strip()

    date_str = date.strftime("%Y-%m-%dT%H:%M:%SZ")
    tags_yaml = "\n".join(f'  - "{tag}"' for tag in tags)

    frontmatter = f'''---
title: "{safe_title}"
date: {date_str}
source_url: "{source_url}"
source_name: "{source_name}"
summary: "{safe_summary}"
image: "{image_path}"
tags:
{tags_yaml}
'''

    if author:
        frontmatter += f'author: "{author}"\n'

    frontmatter += "---\n"

    body = f"\n{summary}\n\n[Read the full article at {source_name}]({source_url})\n"

    return frontmatter + body


def save_article(article: Article, summary: str, tags: list[str], image_path: str) -> Path:
    """Save a processed article as a Hugo markdown file."""
    date_prefix = article.published.strftime("%Y-%m-%d")
    slug = slugify(article.title)
    filename = f"{date_prefix}-{slug}.md"

    content_dir = Path(__file__).parent.parent / "content" / "articles"
    content_dir.mkdir(parents=True, exist_ok=True)

    markdown = generate_markdown(
        title=article.title,
        date=article.published,
        source_url=article.url,
        source_name=article.source_name,
        summary=summary,
        image_path=image_path,
        tags=tags,
        author=article.author
    )

    file_path = content_dir / filename
    file_path.write_text(markdown, encoding="utf-8")

    return file_path


def process_articles(articles: list[Article], max_articles: int = 50) -> list[Path]:
    """Process a batch of articles and generate markdown files."""
    create_placeholder_image()

    generated_files = []
    ai_enabled = os.environ.get("OPENAI_API_KEY") is not None

    if ai_enabled:
        print("  AI mode: ON (using GPT-4o-mini for summaries and tags)")
    else:
        print("  AI mode: OFF (set OPENAI_API_KEY for AI features)")

    for i, article in enumerate(articles[:max_articles]):
        print(f"\nProcessing {i+1}/{min(len(articles), max_articles)}: {article.title[:50]}...")

        try:
            # Generate summary (AI or fallback)
            summary = summarize_article(
                title=article.title,
                description=article.description,
                source_name=article.source_name
            )

            # Generate tags (AI or fallback)
            tags = auto_tag(
                title=article.title,
                description=article.description,
                source_name=article.source_name
            )

            # Process image
            date_str = article.published.strftime("%Y-%m-%d")
            image_path = process_article_image(
                image_url=article.image_url,
                article_title=article.title,
                date_str=date_str,
                fallback_html=article.description
            )

            # Save article
            file_path = save_article(article, summary, tags, image_path)
            generated_files.append(file_path)
            print(f"  -> Saved: {file_path.name}")
            print(f"     Tags: {', '.join(tags)}")

        except Exception as e:
            print(f"  -> Error processing article: {e}")
            continue

    return generated_files


def run_pipeline(extract_themes: bool = False, max_articles: int = 50) -> None:
    """Run the full content pipeline.

    Args:
        extract_themes: Whether to run theme extraction after processing
        max_articles: Maximum articles to process per run
    """
    print("=" * 60)
    print("Windknots Content Pipeline")
    print("=" * 60)

    # Fetch content
    print("\n[1/3] Fetching content from sources...")
    articles = fetch_all_content()

    if not articles:
        print("No new articles found.")
    else:
        # Process and generate
        print(f"\n[2/3] Processing {len(articles)} articles...")
        generated = process_articles(articles, max_articles)
        print(f"\nGenerated {len(generated)} article files.")

    # Theme extraction
    if extract_themes:
        print("\n[3/3] Extracting themes from recent articles...")
        if os.environ.get("OPENAI_API_KEY"):
            theme_files = extract_and_save_themes(min_articles=3)
            print(f"Generated {len(theme_files)} theme posts.")
        else:
            print("Skipping theme extraction (requires OPENAI_API_KEY)")
    else:
        print("\n[3/3] Skipping theme extraction (use --themes to enable)")

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Windknots Content Pipeline")
    parser.add_argument(
        "--themes",
        action="store_true",
        help="Extract themes from recent articles"
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=50,
        help="Maximum articles to process (default: 50)"
    )
    parser.add_argument(
        "--themes-only",
        action="store_true",
        help="Only run theme extraction, skip article fetching"
    )
    parser.add_argument(
        "--digest",
        action="store_true",
        help="Generate a daily digest (themes + weblinks)"
    )
    parser.add_argument(
        "--digest-date",
        type=str,
        help="Date for digest (YYYY-MM-DD, defaults to today)"
    )

    args = parser.parse_args()

    if args.themes_only:
        print("=" * 60)
        print("Windknots Theme Extraction")
        print("=" * 60)
        if os.environ.get("OPENAI_API_KEY"):
            theme_files = extract_and_save_themes(min_articles=3)
            print(f"\nGenerated {len(theme_files)} theme posts.")
        else:
            print("Theme extraction requires OPENAI_API_KEY")
    else:
        # Always fetch and process new articles first
        run_pipeline(extract_themes=args.themes, max_articles=args.max_articles)

        # Then generate digest if requested
        if args.digest:
            from datetime import date
            target_date = None
            if args.digest_date:
                try:
                    target_date = date.fromisoformat(args.digest_date)
                except ValueError:
                    print(f"Invalid date format: {args.digest_date}. Use YYYY-MM-DD.")
                    exit(1)
            generate_daily_digest(target_date=target_date)

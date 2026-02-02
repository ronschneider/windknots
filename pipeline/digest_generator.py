"""Generate daily digest files combining themes and weblinks."""

import argparse
import json
import os
from datetime import datetime, date
from pathlib import Path

import yaml

from .theme_extractor import classify_category, extract_themes_data
from .weblinks_fetcher import fetch_all_weblinks

# ---------------------------------------------------------------------------
# Featured story rotation
# ---------------------------------------------------------------------------

ROTATION_PATH = Path(__file__).parent.parent / "data" / "featured_rotation.json"


def load_rotation_state() -> dict:
    """Load the featured-category rotation state from disk.

    Returns:
        Dict with 'last_category' (str) and 'history' (list of recent
        featured categories, newest first).
    """
    if ROTATION_PATH.exists():
        try:
            with open(ROTATION_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_category": "", "history": []}


def save_rotation_state(state: dict) -> None:
    """Persist the rotation state to disk.

    Args:
        state: Dict with 'last_category' and 'history'
    """
    ROTATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ROTATION_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def pick_featured_theme(themes: list[dict]) -> list[dict]:
    """Reorder themes so index 0 rotates categories day-to-day.

    Rules:
    - Never repeat the same category in featured position two days in a row
    - Prefer categories that haven't been featured recently (least-recent-first)
    - Among eligible themes, prefer higher quality_score
    - Fallback: if all themes are same category, pick the best one anyway

    Args:
        themes: List of theme dicts (must have 'title' and 'tags')

    Returns:
        Reordered copy of themes with the featured theme at index 0
    """
    if not themes:
        return themes

    state = load_rotation_state()
    last_cat = state.get("last_category", "")
    history = state.get("history", [])

    # Classify each theme
    categorized = []
    for t in themes:
        cat = classify_category(t.get("title", ""), t.get("tags", []))
        categorized.append((t, cat))

    # Score each theme for featured eligibility
    def featured_sort_key(item):
        theme, cat = item
        # Penalty if same as yesterday
        same_as_last = 1 if cat == last_cat else 0
        # How recently was this category featured? (lower = more recent = worse)
        try:
            recency = history.index(cat)
        except ValueError:
            recency = len(history) + 1  # never featured = best
        quality = theme.get("quality_score", 5)
        # Sort: first by not-same-as-last (0 before 1 inverted), then by
        # least-recently-featured (higher recency first), then quality desc
        return (same_as_last, -recency, -quality)

    categorized.sort(key=featured_sort_key)

    featured_theme, featured_cat = categorized[0]

    # Rebuild the list: featured first, rest in original order
    result = [featured_theme]
    for t in themes:
        if t is not featured_theme:
            result.append(t)

    # Update rotation state
    new_history = [featured_cat] + [c for c in history if c != featured_cat]
    new_history = new_history[:10]  # keep last 10
    save_rotation_state({
        "last_category": featured_cat,
        "history": new_history,
    })

    print(f"  Featured category: {featured_cat} ('{featured_theme.get('title', '')}')")

    return result


def generate_daily_digest(
    target_date: date = None,
    min_articles_per_theme: int = 2,
    skip_themes: bool = False,
    skip_weblinks: bool = False
) -> Path:
    """Generate a daily digest file combining themes and weblinks.

    Args:
        target_date: Date for the digest (defaults to today)
        min_articles_per_theme: Minimum articles needed per theme
        skip_themes: Skip theme generation (useful for testing)
        skip_weblinks: Skip weblinks fetching (useful for testing)

    Returns:
        Path to the generated digest file
    """
    if target_date is None:
        target_date = date.today()

    print("=" * 60)
    print(f"Generating Daily Digest for {target_date}")
    print("=" * 60)

    # Generate themes
    themes = []
    if not skip_themes:
        print("\n[1/2] Extracting themes...")
        if os.environ.get("OPENAI_API_KEY"):
            themes = extract_themes_data(min_articles=min_articles_per_theme, days=7)
            print(f"Generated {len(themes)} themes")
        else:
            print("Skipping themes (requires OPENAI_API_KEY)")
    else:
        print("\n[1/2] Skipping themes (--skip-themes)")

    # Fetch weblinks
    weblinks = {"reddit": [], "deals": [], "trips": []}
    if not skip_weblinks:
        print("\n[2/2] Fetching weblinks...")
        weblinks = fetch_all_weblinks()
    else:
        print("\n[2/2] Skipping weblinks (--skip-weblinks)")

    # Rotate featured story
    if themes:
        print("\nRotating featured story...")
        themes = pick_featured_theme(themes)

    # Build the digest content
    digest_data = build_digest_frontmatter(target_date, themes, weblinks)

    # Save the digest file
    file_path = save_digest(target_date, digest_data)

    print("\n" + "=" * 60)
    print(f"Digest saved: {file_path}")
    print("=" * 60)

    return file_path


def build_digest_frontmatter(
    target_date: date,
    themes: list[dict],
    weblinks: dict
) -> dict:
    """Build the frontmatter data structure for a digest.

    Args:
        target_date: Date for the digest
        themes: List of theme data dicts
        weblinks: Dict with reddit, deals, trips lists

    Returns:
        Dict ready for YAML serialization
    """
    formatted_date = target_date.strftime("%B %d, %Y")

    return {
        "title": f"Daily Digest - {formatted_date}",
        "date": datetime.combine(target_date, datetime.min.time()).isoformat() + "Z",
        "type": "digest",
        "themes": themes,
        "weblinks": weblinks
    }


def save_digest(target_date: date, digest_data: dict) -> Path:
    """Save a digest as a Hugo markdown file.

    Args:
        target_date: Date for the digest filename
        digest_data: Frontmatter data dict

    Returns:
        Path to saved file
    """
    content_dir = Path(__file__).parent.parent / "content" / "digests"
    content_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{target_date.isoformat()}.md"

    # Custom YAML representer for clean multiline strings
    def str_representer(dumper, data):
        if '\n' in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)

    yaml.add_representer(str, str_representer)

    # Build the markdown file
    frontmatter = yaml.dump(
        digest_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000  # Prevent line wrapping
    )

    markdown = f"---\n{frontmatter}---\n"

    file_path = content_dir / filename
    file_path.write_text(markdown, encoding="utf-8")

    return file_path


def main():
    """CLI entry point for digest generation."""
    parser = argparse.ArgumentParser(
        description="Generate Windknots Daily Digest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m pipeline.digest_generator                  # Generate today's digest
  python -m pipeline.digest_generator --date 2026-01-25
  python -m pipeline.digest_generator --skip-themes    # Only weblinks
  python -m pipeline.digest_generator --skip-weblinks  # Only themes
        """
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Date for digest (YYYY-MM-DD format, defaults to today)"
    )
    parser.add_argument(
        "--skip-themes",
        action="store_true",
        help="Skip theme extraction"
    )
    parser.add_argument(
        "--skip-weblinks",
        action="store_true",
        help="Skip weblinks fetching"
    )
    parser.add_argument(
        "--min-articles",
        type=int,
        default=2,
        help="Minimum articles per theme (default: 2)"
    )

    args = parser.parse_args()

    # Parse date if provided
    target_date = None
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            return

    generate_daily_digest(
        target_date=target_date,
        min_articles_per_theme=args.min_articles,
        skip_themes=args.skip_themes,
        skip_weblinks=args.skip_weblinks
    )


if __name__ == "__main__":
    main()

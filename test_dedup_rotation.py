"""Test theme deduplication and featured-story rotation locally.

Generates 3 fake days of themes + digests using the new dedup/rotation
logic, then optionally runs Hugo to verify the site builds.

No API keys needed — everything is synthetic.

Usage:
    python test_dedup_rotation.py          # generate fake data + try hugo
    python test_dedup_rotation.py --clean  # remove generated test files
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Make sure the pipeline package is importable
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.theme_extractor import (
    classify_category,
    extract_topic_keywords,
    filter_duplicate_themes,
    load_recent_themes,
)
from pipeline.digest_generator import (
    build_digest_frontmatter,
    pick_featured_theme,
    save_digest,
    ROTATION_PATH,
)

ROOT = Path(__file__).parent
THEMES_DIR = ROOT / "content" / "themes"
DIGESTS_DIR = ROOT / "content" / "digests"

# ---------------------------------------------------------------------------
# Fake theme data — 3 days, deliberately heavy on streamers to stress dedup
# ---------------------------------------------------------------------------

FAKE_DAYS: list[dict] = [
    {
        "date": date(2026, 2, 1),
        "ai_output": [
            {
                "title": "Streamers Unleashed: Winter Retrieves for River Trout",
                "description": "New streamer retrieve patterns for cold-water trout.",
                "tags": ["streamers", "trout", "winter"],
                "quality_score": 8,
                "article_indices": [0, 1, 2],
            },
            {
                "title": "Midge Magic: Micro-Patterns for Tailwater Success",
                "description": "Tiny flies, big results on pressured tailwaters.",
                "tags": ["fly tying", "trout", "winter"],
                "quality_score": 7,
                "article_indices": [3, 4],
            },
            {
                "title": "Permit on the Brain: Spring Flats Preview",
                "description": "Planning your spring permit trip early.",
                "tags": ["saltwater", "permit", "destination"],
                "quality_score": 7,
                "article_indices": [5, 6],
            },
        ],
    },
    {
        "date": date(2026, 2, 2),
        "ai_output": [
            {
                "title": "Streamer Presentation: The Art of the Swing",
                "description": "Swinging streamers for steelhead and trout.",
                "tags": ["streamers", "techniques", "steelhead"],
                "quality_score": 9,
            },
            {
                "title": "Conservation Crossroads: Hatchery vs. Wild Debate Heats Up",
                "description": "New data fuels the hatchery-versus-wild discussion.",
                "tags": ["conservation", "steelhead"],
                "quality_score": 8,
            },
            {
                "title": "Rod Quiver Goals: Matching Gear to Water Type",
                "description": "Building a versatile rod lineup for varied conditions.",
                "tags": ["gear", "rods"],
                "quality_score": 6,
            },
        ],
    },
    {
        "date": date(2026, 2, 3),
        "ai_output": [
            {
                "title": "Streamers: The Art of Presentation for Trophy Trout",
                "description": "Yet another streamer article the AI loves.",
                "tags": ["streamers", "trout"],
                "quality_score": 8,
            },
            {
                "title": "Euro Nymphing in High Gradient Pocket Water",
                "description": "Technical nymphing tactics for steep mountain streams.",
                "tags": ["nymphing", "euro", "trout"],
                "quality_score": 8,
            },
            {
                "title": "Beginner's Guide to Reading River Currents",
                "description": "Learning to read water for your first season.",
                "tags": ["beginner", "trout"],
                "quality_score": 7,
            },
        ],
    },
]

# Fake articles just so theme pages have something to reference
FAKE_ARTICLES = [
    {"filename": f"2026-02-01-fake-article-{i}.md", "title": f"Fake Article {i}",
     "source_name": "Test Source", "summary": f"Summary for article {i}."}
    for i in range(7)
]

# Track files we create so --clean can remove them
CREATED_FILES: list[Path] = []


def save_fake_theme(d: date, theme: dict, idx: int) -> Path:
    """Save a single fake theme markdown file."""
    THEMES_DIR.mkdir(parents=True, exist_ok=True)

    slug = theme["title"].lower()
    slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
    slug = "-".join(slug.split())[:50]
    filename = f"{d.isoformat()}-{slug}.md"

    tags_yaml = "\n".join(f'  - "{t}"' for t in theme.get("tags", []))

    markdown = f'''---
title: "{theme["title"]}"
date: {d.isoformat()}T08:00:00Z
type: "theme"
description: "{theme["description"]}"
image: "/images/placeholder.jpg"
tags:
{tags_yaml}
related_articles:
  - "2026-02-01-fake-article-0"
---

{theme["description"]}

## Related Articles

{{{{< theme-articles >}}}}
'''
    path = THEMES_DIR / filename
    path.write_text(markdown, encoding="utf-8")
    CREATED_FILES.append(path)
    return path


def simulate_day(day_data: dict, day_num: int) -> None:
    """Simulate one day of the pipeline for the given fake data."""
    d = day_data["date"]
    ai_themes = day_data["ai_output"]

    print(f"\n{'='*60}")
    print(f"DAY {day_num}: {d}")
    print(f"{'='*60}")

    # 1. Load recent themes (real function — picks up previously saved fakes)
    recent = load_recent_themes(days=7)
    print(f"  Recent themes loaded: {len(recent)}")
    for r in recent:
        print(f"    - [{r['category']}] {r['title']}")

    # 2. Show what the AI "returned"
    print(f"\n  AI returned {len(ai_themes)} themes:")
    for t in ai_themes:
        cat = classify_category(t["title"], t.get("tags", []))
        kw = extract_topic_keywords(t["title"])
        print(f"    [{cat}] {t['title']}")
        print(f"           keywords: {kw}")

    # 3. Run fuzzy dedup filter
    if recent:
        before = len(ai_themes)
        ai_themes = filter_duplicate_themes(ai_themes, recent)
        print(f"\n  After dedup: {len(ai_themes)}/{before} themes kept")
    else:
        print(f"\n  No recent themes — skipping dedup")

    if not ai_themes:
        print("  WARNING: All themes were rejected! Nothing to publish.")
        return

    # 4. Build theme data with fake articles
    theme_data_list = []
    for t in ai_themes:
        theme_data_list.append({
            "title": t["title"],
            "description": t["description"],
            "editorial_intro": t["description"],
            "image": "/images/placeholder.jpg",
            "tags": t.get("tags", []),
            "articles": FAKE_ARTICLES[:3],
            "takeaways": ["Takeaway 1", "Takeaway 2"],
            "url": f"/themes/{d.isoformat()}-test/",
            "quality_score": t.get("quality_score", 5),
        })

    # 5. Featured rotation
    print(f"\n  Running featured rotation...")
    theme_data_list = pick_featured_theme(theme_data_list)
    print(f"  Final theme order:")
    for i, t in enumerate(theme_data_list):
        cat = classify_category(t["title"], t.get("tags", []))
        marker = " *** FEATURED ***" if i == 0 else ""
        print(f"    {i+1}. [{cat}] {t['title']}{marker}")

    # 6. Save theme files (so next day's load_recent_themes picks them up)
    for idx, t in enumerate(ai_themes):
        path = save_fake_theme(d, t, idx)
        print(f"  Saved: {path.name}")

    # 7. Save digest
    digest_data = build_digest_frontmatter(d, theme_data_list, {"reddit": [], "deals": [], "trips": []})
    digest_path = save_digest(d, digest_data)
    CREATED_FILES.append(digest_path)
    print(f"  Digest: {digest_path.name}")


def run_hugo_check() -> bool:
    """Try to build Hugo site to verify no template errors."""
    import subprocess
    print(f"\n{'='*60}")
    print("HUGO BUILD CHECK")
    print(f"{'='*60}")
    try:
        result = subprocess.run(
            ["hugo", "--minify"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print("  Hugo build succeeded!")
            # Count pages
            for line in result.stderr.splitlines():
                if line.strip():
                    print(f"  {line.strip()}")
            return True
        else:
            print(f"  Hugo build FAILED (exit {result.returncode})")
            print(result.stderr[-500:] if result.stderr else "(no stderr)")
            return False
    except FileNotFoundError:
        print("  Hugo not installed — skipping build check.")
        print("  Install Hugo to verify: https://gohugo.io/installation/")
        return True  # not a failure of our code


def clean_test_files():
    """Remove test-generated files."""
    # Remove any themes/digests for Feb 1-3 2026
    count = 0
    for d in [date(2026, 2, 1), date(2026, 2, 2), date(2026, 2, 3)]:
        prefix = d.isoformat()
        for f in THEMES_DIR.glob(f"{prefix}-*.md"):
            f.unlink()
            print(f"  Removed: {f.name}")
            count += 1
        digest = DIGESTS_DIR / f"{prefix}.md"
        if digest.exists():
            digest.unlink()
            print(f"  Removed: {digest.name}")
            count += 1

    # Remove rotation state
    if ROTATION_PATH.exists():
        ROTATION_PATH.unlink()
        print(f"  Removed: {ROTATION_PATH.name}")
        count += 1

    print(f"\nCleaned {count} test files.")


def main():
    parser = argparse.ArgumentParser(description="Test dedup + rotation locally")
    parser.add_argument("--clean", action="store_true", help="Remove generated test files")
    parser.add_argument("--no-hugo", action="store_true", help="Skip Hugo build check")
    args = parser.parse_args()

    if args.clean:
        clean_test_files()
        return

    # Clear any previous rotation state so test is reproducible
    if ROTATION_PATH.exists():
        ROTATION_PATH.unlink()

    # Clear any previous test theme files for these dates
    for d in [date(2026, 2, 1), date(2026, 2, 2), date(2026, 2, 3)]:
        for f in THEMES_DIR.glob(f"{d.isoformat()}-*.md"):
            f.unlink()
        digest = DIGESTS_DIR / f"{d.isoformat()}.md"
        if digest.exists():
            digest.unlink()

    print("Testing theme deduplication + featured rotation")
    print("=" * 60)

    # Run 3 simulated days
    for i, day_data in enumerate(FAKE_DAYS, 1):
        simulate_day(day_data, i)

    # Show final rotation state
    print(f"\n{'='*60}")
    print("ROTATION STATE")
    print(f"{'='*60}")
    if ROTATION_PATH.exists():
        state = json.loads(ROTATION_PATH.read_text())
        print(f"  Last featured category: {state['last_category']}")
        print(f"  History: {state['history']}")
    else:
        print("  (no rotation file created — something is wrong)")

    # Hugo build check
    if not args.no_hugo:
        run_hugo_check()

    print(f"\n{'='*60}")
    print("DONE — run 'python test_dedup_rotation.py --clean' to remove test files")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

"""AI-powered tagging system for fishing articles."""

import os
import re
from typing import Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


# Available tags for the fly fishing site
VALID_TAGS = [
    "trout",
    "salmon",
    "steelhead",
    "saltwater",
    "warmwater",
    "dry-fly",
    "nymphing",
    "streamers",
    "fly-tying",
    "gear",
    "techniques",
    "travel",
    "conservation",
    "beginner",
    "spey",
    "euro-nymph",
    "hatches",
    "rivers",
    "stillwater",
]

# Tag descriptions for AI context
TAG_DESCRIPTIONS = {
    "trout": "Rainbow, brown, brook, cutthroat, golden trout fishing",
    "salmon": "Atlantic salmon, Pacific salmon, landlocked salmon",
    "steelhead": "Steelhead fishing, Great Lakes or coastal",
    "saltwater": "Bonefish, tarpon, permit, stripers, and other saltwater fly fishing",
    "warmwater": "Bass, carp, pike on the fly",
    "dry-fly": "Dry fly fishing, surface takes, rising fish",
    "nymphing": "Nymph fishing, euro-nymphing, indicator fishing",
    "streamers": "Streamer fishing, big fly tactics, stripping flies",
    "fly-tying": "Tying flies, patterns, materials, tutorials",
    "gear": "Fly rods, reels, lines, waders, packs, accessories reviews",
    "techniques": "Casting, presentation, reading water, approach",
    "travel": "Fly fishing destinations, lodges, guides, trip reports",
    "conservation": "Habitat, catch-and-release, wild fish, environmental issues",
    "beginner": "Getting started, basics, learning to fly fish",
    "spey": "Spey casting, two-handed rods, swinging flies",
    "euro-nymph": "Euro nymphing, tight-line, Czech nymphing",
    "hatches": "Insect hatches, matching the hatch, entomology",
    "rivers": "River fishing, freestone streams, tailwaters, spring creeks",
    "stillwater": "Lake fishing, pond fishing, stillwater tactics",
}


def get_openai_client() -> Optional[OpenAI]:
    """Get OpenAI client if API key is available."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def ai_tag(title: str, description: str, source_name: str = "") -> list[str]:
    """Use AI to intelligently tag an article.

    Args:
        title: Article title
        description: Article description or content
        source_name: Source publication name

    Returns:
        List of relevant tags (2-5 tags)
    """
    client = get_openai_client()

    if not client:
        # Fallback to keyword-based tagging
        return keyword_tag(title, description, source_name)

    # Build tag list with descriptions for AI
    tag_context = "\n".join(f"- {tag}: {desc}" for tag, desc in TAG_DESCRIPTIONS.items())

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": f"""You are a fly fishing content tagger. Analyze fly fishing articles and assign 2-5 relevant tags.

Available tags:
{tag_context}

Rules:
1. Return ONLY a comma-separated list of tags, nothing else
2. Use 2-5 tags that best describe the content
3. Always include at least one species/water tag: trout, salmon, steelhead, saltwater, warmwater
4. Add technique tags (dry-fly, nymphing, streamers, spey, euro-nymph) when relevant
5. Tag "fly-tying" only for articles about tying flies
6. Tag "beginner" for introductory/learning content
7. Tag "hatches" for entomology or matching-the-hatch content"""
                },
                {
                    "role": "user",
                    "content": f"Title: {title}\n\nSource: {source_name}\n\nContent:\n{description[:1500]}"
                }
            ],
            max_tokens=50,
            temperature=0.3
        )

        # Parse response
        tag_text = response.choices[0].message.content.strip().lower()
        tags = [t.strip() for t in tag_text.split(",")]

        # Validate tags - only keep valid ones
        valid_tags = [t for t in tags if t in VALID_TAGS]

        # Ensure we have at least one tag
        if not valid_tags:
            valid_tags = keyword_tag(title, description, source_name)

        return valid_tags[:5]  # Max 5 tags

    except Exception as e:
        print(f"AI tagging error: {e}")
        return keyword_tag(title, description, source_name)


def keyword_tag(title: str, description: str, source_name: str = "") -> list[str]:
    """Fallback keyword-based tagging when AI is unavailable."""
    text = f"{title} {description} {source_name}".lower()
    tags = set()

    # Water type
    freshwater_kw = ["bass", "trout", "walleye", "crappie", "bluegill", "catfish",
                     "pike", "musky", "lake", "river", "pond", "stream"]
    saltwater_kw = ["ocean", "offshore", "inshore", "tarpon", "tuna", "marlin",
                    "snook", "redfish", "grouper", "snapper", "saltwater", "gulf",
                    "coastal", "beach", "reef"]
    flyfish_kw = ["fly fishing", "fly-fishing", "flyfishing", "fly rod", "fly tying",
                  "nymph", "dry fly", "streamer"]

    if any(kw in text for kw in freshwater_kw):
        tags.add("freshwater")
    if any(kw in text for kw in saltwater_kw):
        tags.add("saltwater")
    if any(kw in text for kw in flyfish_kw):
        tags.add("fly-fishing")

    # Content type
    if any(kw in text for kw in ["rod", "reel", "lure", "tackle", "gear", "review", "test"]):
        tags.add("gear")
    if any(kw in text for kw in ["how to", "tip", "technique", "tutorial", "rig", "cast"]):
        tags.add("techniques")
    if any(kw in text for kw in ["destination", "lodge", "trip", "travel", "guide service"]):
        tags.add("travel")
    if any(kw in text for kw in ["tournament", "record", "regulation", "news", "announce"]):
        tags.add("news")
    if any(kw in text for kw in ["conservation", "habitat", "release", "sustainable"]):
        tags.add("conservation")

    # Species
    if "bass" in text and ("largemouth" in text or "smallmouth" in text or "bass fish" in text):
        tags.add("bass")
    if "trout" in text:
        tags.add("trout")
    if "redfish" in text or "red drum" in text:
        tags.add("redfish")
    if "tarpon" in text:
        tags.add("tarpon")

    # Ensure at least one water type tag
    if not tags.intersection({"freshwater", "saltwater", "fly-fishing"}):
        tags.add("freshwater")  # Default

    return sorted(list(tags))[:5]


def auto_tag(title: str, description: str, source_name: str = "") -> list[str]:
    """Main entry point for tagging - uses AI if available, falls back to keywords."""
    return ai_tag(title, description, source_name)


def get_primary_tag(tags: list[str]) -> str:
    """Get the primary/most important tag for an article."""
    # Priority order for primary tag
    priority = ["tarpon", "redfish", "bass", "trout", "saltwater", "freshwater",
                "fly-fishing", "offshore", "inshore", "news", "techniques",
                "gear", "travel", "conservation"]

    for p_tag in priority:
        if p_tag in tags:
            return p_tag

    return tags[0] if tags else "freshwater"


if __name__ == "__main__":
    # Test AI tagging
    test_cases = [
        {
            "title": "Sight Casting to Tailing Redfish on the Texas Flats",
            "description": "Learn the best techniques for stalking and casting to redfish tailing in shallow water on the Texas coast.",
            "source_name": "Salt Water Sportsman"
        },
        {
            "title": "New Shimano Curado MGL Review",
            "description": "We test the latest baitcasting reel from Shimano, perfect for bass fishing applications.",
            "source_name": "Bassmaster"
        },
        {
            "title": "Matching the Hatch: Spring Mayfly Patterns",
            "description": "Top dry fly patterns for matching early season mayfly hatches on Western trout streams.",
            "source_name": "Fly Fisherman"
        }
    ]

    print("Testing AI tagger:")
    for test in test_cases:
        tags = auto_tag(test["title"], test["description"], test["source_name"])
        print(f"\nTitle: {test['title']}")
        print(f"Tags: {tags}")

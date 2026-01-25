"""AI-powered article summarization using OpenAI."""

import os
import re
from typing import Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


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
def summarize_article(title: str, description: str, source_name: str) -> str:
    """Generate an engaging 2-3 sentence summary of an article.

    Args:
        title: Article title
        description: Article description or excerpt
        source_name: Name of the source publication

    Returns:
        AI-generated summary or fallback to cleaned description
    """
    client = get_openai_client()

    if not client:
        return clean_description(description)

    # Skip if no content to summarize
    if not description or len(description.strip()) < 50:
        return clean_description(description) if description else f"Read more about {title}."

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are an expert fly fishing editor writing summaries for a dedicated fly fishing audience.

Write a 2-3 sentence summary that:
1. Leads with the most interesting or actionable insight
2. Includes specific details (species, fly patterns, water types, techniques)
3. Uses fly fishing terminology naturally
4. Makes the reader want to click through to the full article

Style:
- Write like an experienced fly angler talking to other fly fishers
- Be specific about flies, hatches, and techniques
- Use terms like "tight lines," "rising fish," "dead drift," "strip set" naturally
- Avoid phrases like "This article discusses" or "The author explains"
- Don't start with "In this article" or similar meta-commentary
- Keep it punchy and informative"""
                },
                {
                    "role": "user",
                    "content": f"Title: {title}\n\nSource: {source_name}\n\nContent:\n{description[:2000]}"
                }
            ],
            max_tokens=150,
            temperature=0.7
        )

        summary = response.choices[0].message.content.strip()

        # Clean up any quotes the model might add
        summary = summary.strip('"')

        return summary

    except Exception as e:
        print(f"Error summarizing article: {e}")
        return clean_description(description)


def clean_description(description: str) -> str:
    """Clean up raw description text for fallback use."""
    if not description:
        return ""

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', description)

    # Remove "The post X appeared first on Y" boilerplate
    text = re.sub(r'The post .+ appeared first on .+\.?', '', text, flags=re.IGNORECASE)

    # Clean up whitespace
    text = ' '.join(text.split())

    # Truncate if too long
    if len(text) > 300:
        # Try to break at sentence
        sentences = text[:350].split('. ')
        if len(sentences) > 1:
            text = '. '.join(sentences[:-1]) + '.'
        else:
            text = text[:297] + "..."

    return text.strip()


def generate_editorial_intro(articles: list, theme: str) -> str:
    """Generate an editorial introduction for a themed collection of articles.

    Args:
        articles: List of article dicts with title, description, source_name
        theme: The identified theme connecting these articles

    Returns:
        Editorial intro paragraph
    """
    client = get_openai_client()

    if not client:
        return f"This week's roundup focuses on {theme}."

    # Build article summaries for context
    article_context = "\n\n".join(
        f"- {a['title']} ({a['source_name']}): {a['description'][:200]}..."
        for a in articles[:5]
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are the editor of a fishing content aggregator. Write a brief editorial introduction
(2-3 sentences) that ties together related articles around a common theme.

Be conversational and insightful - point out interesting patterns or takeaways.
Don't just list what the articles are about; offer perspective on why this matters to anglers."""
                },
                {
                    "role": "user",
                    "content": f"Theme: {theme}\n\nRelated articles:\n{article_context}"
                }
            ],
            max_tokens=150,
            temperature=0.8
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"Error generating editorial intro: {e}")
        return f"This week's roundup focuses on {theme}."


if __name__ == "__main__":
    # Test summarization
    test_summary = summarize_article(
        title="Record Striped Bass Caught in Chesapeake Bay",
        description="A fisherman from Maryland landed a 67-pound striped bass in the Chesapeake Bay last weekend, setting a new state record. The fish was caught using live eels as bait near the Bay Bridge during the early morning hours. Wildlife officials verified the catch and the angler plans to have the fish mounted.",
        source_name="Field & Stream"
    )
    print(f"Summary: {test_summary}")

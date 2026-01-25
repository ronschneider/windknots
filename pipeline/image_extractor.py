"""Extract and cache article images."""

import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from PIL import Image


# Maximum image dimensions
MAX_WIDTH = 800
MAX_HEIGHT = 600
QUALITY = 85

# Supported image formats
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Placeholder image path (relative to Hugo static)
PLACEHOLDER_IMAGE = "/images/placeholder.jpg"


def get_image_dir(date_str: str) -> Path:
    """Get the image directory for a given date (YYYY-MM-DD)."""
    year, month, _ = date_str.split("-")[:3]
    img_dir = Path(__file__).parent.parent / "static" / "images" / year / month
    img_dir.mkdir(parents=True, exist_ok=True)
    return img_dir


def generate_image_filename(url: str, title: str) -> str:
    """Generate a unique filename for an image."""
    # Create hash from URL for uniqueness
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]

    # Create slug from title
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower())[:30].strip('-')

    # Get extension from URL
    parsed = urlparse(url)
    ext = Path(parsed.path).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        ext = ".jpg"

    return f"{slug}-{url_hash}{ext}"


def download_and_resize_image(url: str, output_path: Path) -> bool:
    """Download an image and resize it if necessary.

    Args:
        url: URL of the image to download
        output_path: Path where the image should be saved

    Returns:
        True if successful, False otherwise
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                print(f"Invalid content type: {content_type}")
                return False

            # Open and process image
            img = Image.open(BytesIO(response.content))

            # Convert RGBA to RGB if needed (for JPEG output)
            if img.mode in ("RGBA", "P") and output_path.suffix.lower() in (".jpg", ".jpeg"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Resize if too large
            if img.width > MAX_WIDTH or img.height > MAX_HEIGHT:
                img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)

            # Save
            img.save(output_path, quality=QUALITY, optimize=True)
            return True

    except Exception as e:
        print(f"Error downloading image {url}: {e}")
        return False


def extract_og_image(html: str) -> Optional[str]:
    """Extract og:image URL from HTML."""
    # Look for og:image meta tag
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def extract_first_image(html: str) -> Optional[str]:
    """Extract first image URL from HTML content."""
    # Look for img tags
    pattern = r'<img[^>]+src=["\']([^"\']+)["\']'
    match = re.search(pattern, html, re.IGNORECASE)

    if match:
        url = match.group(1)
        # Filter out common non-content images
        skip_patterns = [
            "logo", "icon", "avatar", "emoji", "tracking", "pixel",
            "ad", "banner", "button", "sprite", "spacer"
        ]
        if not any(skip in url.lower() for skip in skip_patterns):
            return url

    return None


def process_article_image(
    image_url: Optional[str],
    article_title: str,
    date_str: str,
    fallback_html: str = ""
) -> str:
    """Process an article's image, downloading and caching it.

    Args:
        image_url: Direct URL to image (from feed/API)
        article_title: Title of the article (for filename)
        date_str: Date string (YYYY-MM-DD) for directory organization
        fallback_html: HTML content to extract image from if no direct URL

    Returns:
        Relative path to image for Hugo (e.g., "/images/2024/01/article-abc123.jpg")
        or placeholder path if no image found
    """
    # Try to find image URL
    url = image_url

    if not url and fallback_html:
        # Try og:image first
        url = extract_og_image(fallback_html)

        # Fall back to first image in content
        if not url:
            url = extract_first_image(fallback_html)

    if not url:
        return PLACEHOLDER_IMAGE

    # Ensure URL is absolute
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith("http"):
        return PLACEHOLDER_IMAGE

    # Generate output path
    img_dir = get_image_dir(date_str)
    filename = generate_image_filename(url, article_title)
    output_path = img_dir / filename

    # Check if already cached
    if output_path.exists():
        # Return Hugo-relative path
        rel_path = output_path.relative_to(Path(__file__).parent.parent / "static")
        return f"/{rel_path.as_posix()}"

    # Download and cache
    if download_and_resize_image(url, output_path):
        rel_path = output_path.relative_to(Path(__file__).parent.parent / "static")
        return f"/{rel_path.as_posix()}"

    return PLACEHOLDER_IMAGE


def create_placeholder_image() -> None:
    """Create a placeholder image if it doesn't exist."""
    placeholder_dir = Path(__file__).parent.parent / "static" / "images"
    placeholder_dir.mkdir(parents=True, exist_ok=True)
    placeholder_path = placeholder_dir / "placeholder.jpg"

    if placeholder_path.exists():
        return

    # Create a simple gradient placeholder
    width, height = 800, 450
    img = Image.new("RGB", (width, height))

    # Blue gradient
    for y in range(height):
        for x in range(width):
            # Ocean blue gradient
            r = int(14 + (y / height) * 50)
            g = int(116 + (y / height) * 60)
            b = int(144 + (y / height) * 40)
            img.putpixel((x, y), (r, g, b))

    img.save(placeholder_path, quality=90)
    print(f"Created placeholder image at {placeholder_path}")


if __name__ == "__main__":
    # Create placeholder
    create_placeholder_image()

    # Test image processing
    test_url = "https://via.placeholder.com/1200x800.jpg"
    result = process_article_image(
        image_url=test_url,
        article_title="Test Article Title",
        date_str="2024-01-24"
    )
    print(f"Processed image: {result}")

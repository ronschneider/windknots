#!/usr/bin/env python3
"""Create a placeholder image for articles without images."""

from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow not installed. Run: pip install Pillow")
    exit(1)


def create_placeholder():
    """Create a gradient placeholder image."""
    # Output path
    output_dir = Path(__file__).parent.parent / "static" / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "placeholder.jpg"

    if output_path.exists():
        print(f"Placeholder already exists: {output_path}")
        return

    # Create image
    width, height = 800, 450
    img = Image.new("RGB", (width, height))

    # Blue ocean gradient
    for y in range(height):
        for x in range(width):
            # Gradient from ocean-600 to ocean-800
            progress = y / height
            r = int(2 + progress * 5)       # 2 -> 7
            g = int(132 + progress * (-63))  # 132 -> 69
            b = int(199 + progress * (-66))  # 199 -> 133
            img.putpixel((x, y), (r, g, b))

    img.save(output_path, quality=90)
    print(f"Created placeholder: {output_path}")


if __name__ == "__main__":
    create_placeholder()

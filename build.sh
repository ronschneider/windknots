#!/bin/bash
# Windknots Build Script
# Usage: ./build.sh [--fresh] [--themes]

set -e

cd "$(dirname "$0")"

# Parse arguments
FRESH=false
THEMES=false
for arg in "$@"; do
    case $arg in
        --fresh) FRESH=true ;;
        --themes) THEMES=true ;;
    esac
done

echo "============================================"
echo "Windknots Build Script"
echo "============================================"

# Check for API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY not set - running in fallback mode"
else
    echo "✓ OPENAI_API_KEY detected"
fi

# Fresh rebuild - clear everything
if [ "$FRESH" = true ]; then
    echo ""
    echo "[1/4] Fresh rebuild - clearing old content..."
    rm -f content/articles/2*.md
    echo "[]" > data/seen_urls.json
    echo "  Cleared articles and seen URLs"
else
    echo ""
    echo "[1/4] Incremental build (use --fresh to clear old content)"
fi

# Build CSS
echo ""
echo "[2/4] Building Tailwind CSS..."
npm run build:css

# Run content pipeline
echo ""
echo "[3/4] Running content pipeline..."
if [ "$THEMES" = true ]; then
    python -m pipeline.generator --themes
else
    python -m pipeline.generator
fi

# Build Hugo
echo ""
echo "[4/4] Building Hugo site..."
hugo --minify

echo ""
echo "============================================"
echo "Build complete! Output in ./public/"
echo "============================================"
echo ""
echo "To preview locally: hugo server -D"
echo "To deploy: push to GitHub (if Pages configured)"

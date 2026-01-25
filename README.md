# Windknots

A static website that automatically aggregates fishing content from around the web, generates AI summaries, and publishes daily to GitHub Pages.

## Features

- **Automated Content Aggregation**: Fetches from RSS feeds, NewsAPI, and Reddit
- **AI Summarization**: Uses GPT-4o-mini to generate concise article summaries
- **Auto-Tagging**: Automatically categorizes content by topic
- **Infinite Scroll**: Smooth endless browsing experience
- **Tag Filtering**: Filter articles by category
- **Responsive Design**: Works great on mobile and desktop
- **Daily Updates**: GitHub Actions cron job fetches fresh content daily

## Tech Stack

- **Static Site Generator**: Hugo
- **Content Pipeline**: Python
- **Styling**: Tailwind CSS
- **AI**: OpenAI GPT-4o-mini
- **Hosting**: GitHub Pages
- **Automation**: GitHub Actions

## Project Structure

```
windknots/
├── .github/workflows/     # GitHub Actions workflow
├── content/articles/      # Generated markdown articles
├── data/                  # Configuration and tracking
├── pipeline/              # Python content pipeline
├── themes/windknots/      # Hugo theme
└── config.toml           # Hugo configuration
```

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Hugo (extended version)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/windknots.git
   cd windknots
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Node dependencies:
   ```bash
   npm install
   ```

4. Build Tailwind CSS:
   ```bash
   npm run build:css
   ```

### Configuration

1. Set environment variables:
   ```bash
   export OPENAI_API_KEY=your_openai_key
   export NEWS_API_KEY=your_newsapi_key
   ```

2. Edit `data/sources.json` to configure content sources

### Running Locally

1. Run the content pipeline:
   ```bash
   python -m pipeline.generator
   ```

2. Start Hugo development server:
   ```bash
   hugo server -D
   ```

3. Open http://localhost:1313

### GitHub Actions

The workflow runs daily at 6 AM UTC. To set up:

1. Add secrets to your GitHub repository:
   - `OPENAI_API_KEY`
   - `NEWS_API_KEY`

2. Enable GitHub Pages in repository settings

3. Configure custom domain (optional):
   - Add CNAME record pointing to `yourusername.github.io`
   - Update `config.toml` baseURL

## Content Sources

### RSS Feeds
- Field & Stream
- Outdoor Life
- Sport Fishing Magazine
- Fly Fisherman
- In-Fisherman
- Salt Water Sportsman
- Bassmaster

### APIs
- NewsAPI.org (fishing news)
- Reddit (r/fishing, r/flyfishing, r/bassfishing)

## Cost Estimate

| Service | Monthly Cost |
|---------|--------------|
| GitHub Pages | Free |
| NewsAPI.org | Free (100 req/day) |
| OpenAI GPT-4o-mini | ~$5-10 |
| **Total** | **~$5-10/month** |

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

"""Fetch fishing reports from Orvis fishing reports site."""

import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


@dataclass
class FishingReport:
    """A fishing report from a river/location."""
    name: str
    url: str
    state: str
    region: str
    lat: float
    lon: float
    water_temp: Optional[str] = None
    conditions: Optional[str] = None
    updated: Optional[str] = None
    source: Optional[str] = None
    flies: Optional[str] = None
    rating: Optional[str] = None


BASE_URL = "https://fishingreports.orvis.com"

REGIONS = {
    "northeast": ["connecticut", "maine", "massachusetts", "new-hampshire", "new-jersey",
                  "new-york", "pennsylvania", "rhode-island", "vermont"],
    "southeast": ["alabama", "arkansas", "florida", "georgia", "kentucky", "louisiana",
                  "mississippi", "north-carolina", "south-carolina", "tennessee",
                  "virginia", "west-virginia"],
    "midwest": ["illinois", "indiana", "iowa", "michigan", "minnesota", "missouri",
                "ohio", "wisconsin"],
    "southwest": ["arizona", "new-mexico", "oklahoma", "texas"],
    "west": ["alaska", "california", "colorado", "idaho", "montana", "nevada",
             "oregon", "utah", "washington", "wyoming"],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch_state_rivers(region: str, state: str) -> list[dict]:
    """Fetch list of rivers from a state page.

    Returns list of dicts with name, url, lat, lon for each river.
    """
    rivers = []
    url = f"{BASE_URL}/{region}/{state}"

    try:
        with httpx.Client(timeout=30, headers=HEADERS, follow_redirects=True) as client:
            response = client.get(url)
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "html.parser")

            # Look for JavaScript data containing river info
            scripts = soup.find_all("script")
            for script in scripts:
                if script.string and "dataProvider" in script.string:
                    # Extract the dataProvider array
                    match = re.search(r'dataProvider:\s*\[(.*?)\]', script.string, re.DOTALL)
                    if match:
                        # Parse each river object
                        data_str = match.group(1)
                        # Find all objects in the array
                        objects = re.findall(r'\{[^}]+\}', data_str)
                        for obj_str in objects:
                            try:
                                # Extract fields using regex
                                name_match = re.search(r'location_name:\s*["\']([^"\']+)["\']', obj_str)
                                lat_match = re.search(r'latitude:\s*([-\d.]+)', obj_str)
                                lon_match = re.search(r'longitude:\s*([-\d.]+)', obj_str)
                                alias_match = re.search(r'alias:\s*["\']([^"\']+)["\']', obj_str)

                                if name_match and lat_match and lon_match and alias_match:
                                    rivers.append({
                                        "name": name_match.group(1),
                                        "lat": float(lat_match.group(1)),
                                        "lon": float(lon_match.group(1)),
                                        "alias": alias_match.group(1),
                                        "url": f"{BASE_URL}/{region}/{state}/{alias_match.group(1)}"
                                    })
                            except (ValueError, AttributeError):
                                continue

            # Fallback: parse links if no JS data found
            if not rivers:
                links = soup.select('a[href*="/' + state + '/"]')
                for link in links:
                    href = link.get("href", "")
                    if href.count("/") >= 3 and not href.endswith(state):
                        name = link.get_text(strip=True)
                        if name and len(name) > 2:
                            full_url = urljoin(BASE_URL, href)
                            rivers.append({
                                "name": name,
                                "url": full_url,
                                "lat": 0,
                                "lon": 0,
                                "alias": href.split("/")[-1]
                            })

    except Exception as e:
        print(f"    Error fetching {state}: {e}")

    return rivers


def fetch_river_report(river: dict, region: str, state: str) -> Optional[FishingReport]:
    """Fetch detailed report for a single river."""
    try:
        with httpx.Client(timeout=30, headers=HEADERS, follow_redirects=True) as client:
            response = client.get(river["url"])
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, "html.parser")

            # Extract report details
            water_temp = None
            conditions = None
            updated = None
            source = None
            flies = None
            rating = None
            lat = river.get("lat", 0)
            lon = river.get("lon", 0)

            # Try to get coordinates from page if not in river data
            if lat == 0 or lon == 0:
                scripts = soup.find_all("script")
                for script in scripts:
                    if script.string:
                        lat_match = re.search(r'latitude["\']?\s*[:=]\s*([-\d.]+)', script.string)
                        lon_match = re.search(r'longitude["\']?\s*[:=]\s*([-\d.]+)', script.string)
                        if lat_match and lon_match:
                            lat = float(lat_match.group(1))
                            lon = float(lon_match.group(1))
                            break

            # Water temperature
            temp_el = soup.find(string=re.compile(r'Water Temperature', re.I))
            if temp_el:
                parent = temp_el.find_parent()
                if parent:
                    temp_match = re.search(r'(\d+)\s*°?\s*F', parent.get_text())
                    if temp_match:
                        water_temp = f"{temp_match.group(1)}°F"

            # Last updated
            updated_el = soup.find(string=re.compile(r'Last Updated|Updated', re.I))
            if updated_el:
                parent = updated_el.find_parent()
                if parent:
                    # Look for date pattern
                    date_match = re.search(r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})', parent.get_text())
                    if date_match:
                        updated = date_match.group(1)

            # Report source (guide shop)
            source_el = soup.find(string=re.compile(r'Report Source|Submitted by', re.I))
            if source_el:
                parent = source_el.find_parent()
                if parent:
                    source_text = parent.get_text()
                    # Extract the source name after the label
                    source_match = re.search(r'(?:Report Source|Submitted by)[:\s]+([^,\n]+)', source_text, re.I)
                    if source_match:
                        source = source_match.group(1).strip()

            # Conditions - look for main report text
            conditions_section = soup.select_one("#CurrentConditions, .current-conditions, .report-content")
            if conditions_section:
                paragraphs = conditions_section.find_all("p")
                if paragraphs:
                    conditions = " ".join(p.get_text(strip=True) for p in paragraphs[:2])
                    if len(conditions) > 200:
                        conditions = conditions[:197] + "..."

            # Recommended flies
            flies_section = soup.find(string=re.compile(r'Recommended Flies|Hot Flies|Fly Patterns', re.I))
            if flies_section:
                parent = flies_section.find_parent()
                if parent:
                    # Get sibling or child content
                    next_el = parent.find_next_sibling()
                    if next_el:
                        flies = next_el.get_text(strip=True)[:100]

            # Rating from map legend classes or explicit rating
            rating_el = soup.select_one(".rating, .conditions-rating, [class*='hot-spot'], [class*='excellent']")
            if rating_el:
                rating_class = " ".join(rating_el.get("class", []))
                if "hot" in rating_class.lower():
                    rating = "Hot Spot"
                elif "excellent" in rating_class.lower():
                    rating = "Excellent"
                elif "good" in rating_class.lower():
                    rating = "Good"

            # Skip if we couldn't get coordinates
            if lat == 0 and lon == 0:
                return None

            return FishingReport(
                name=river["name"],
                url=river["url"],
                state=state.replace("-", " ").title(),
                region=region.title(),
                lat=lat,
                lon=lon,
                water_temp=water_temp,
                conditions=conditions,
                updated=updated,
                source=source,
                flies=flies,
                rating=rating
            )

    except Exception as e:
        print(f"      Error fetching {river['name']}: {e}")
        return None


def fetch_all_reports(max_per_state: int = 20) -> list[FishingReport]:
    """Fetch fishing reports from all regions and states.

    Args:
        max_per_state: Maximum rivers to fetch per state (to avoid rate limits)

    Returns:
        List of FishingReport objects
    """
    all_reports = []

    for region, states in REGIONS.items():
        print(f"  Region: {region.title()}")

        for state in states:
            print(f"    State: {state.replace('-', ' ').title()}...", end=" ", flush=True)

            rivers = fetch_state_rivers(region, state)
            print(f"found {len(rivers)} rivers")

            # Limit rivers per state
            rivers = rivers[:max_per_state]

            for river in rivers:
                report = fetch_river_report(river, region, state)
                if report:
                    all_reports.append(report)

                # Be polite to the server
                time.sleep(0.5)

            time.sleep(1)  # Pause between states

    return all_reports


def save_reports(reports: list[FishingReport], output_path: Path):
    """Save reports to JSON file."""
    data = {
        "generated": datetime.now().isoformat(),
        "count": len(reports),
        "reports": [asdict(r) for r in reports]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Saved {len(reports)} reports to {output_path}")


def load_reports(input_path: Path) -> list[dict]:
    """Load reports from JSON file."""
    if not input_path.exists():
        return []

    with open(input_path) as f:
        data = json.load(f)

    return data.get("reports", [])


if __name__ == "__main__":
    print("Fetching Orvis fishing reports...")
    reports = fetch_all_reports(max_per_state=10)

    output_path = Path(__file__).parent.parent / "static" / "data" / "fishing-reports.json"
    save_reports(reports, output_path)

    print(f"\nSample reports:")
    for r in reports[:5]:
        print(f"  {r.name} ({r.state}): {r.water_temp or 'N/A'}, updated {r.updated or 'N/A'}")

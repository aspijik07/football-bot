#!/usr/bin/env python3
"""
Football Broadcast Dashboard Scraper & HTML Generator
Fetches South American football fixtures, TV channels, and 16:9 preview banners.

Key Requirements:
1. Enforce image URL domain replacement on all scraped banners:
   Replaces 'https://www.zerozero.com.ar' and 'https://www.ogol.com.br' with 'https://cdn-img.staticzz.com'
2. Hardcode 'Copa Argentina' and 'Copa do Brasil' into sidebar filters list (even with 0 matches),
   and remove 'Copa Paulista'.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Constants & Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MATCHES_JSON_PATH = os.path.join(BASE_DIR, "matches.json")
INDEX_HTML_PATH = os.path.join(BASE_DIR, "index.html")

DEFAULT_CREST = (
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='60' height='60' "
    "viewBox='0 0 60 60'><circle cx='30' cy='30' r='27' fill='%231e293b' stroke='%2338bdf8' "
    "stroke-width='2.5'/><text x='30' y='36' font-size='20' text-anchor='middle' fill='%2338bdf8' "
    "font-family='system-ui'>⚽</text></svg>"
)

# Sidebar Filter Configuration:
# Hardcoded to explicitly include "Copa Argentina" and "Copa do Brasil" (even with 0 matches),
# and strictly exclude "Copa Paulista".
SIDEBAR_FILTER_LEAGUES = [
    {"name": "Liga Profesional Clausura", "badge_class": "badge-argentina", "country": "Argentina"},
    {"name": "Copa Libertadores", "badge_class": "badge-libertadores", "country": "South America"},
    {"name": "Copa Sudamericana", "badge_class": "badge-sudamericana", "country": "South America"},
    {"name": "Série A", "badge_class": "badge-brazil", "country": "Brazil"},
    {"name": "Copa Argentina", "badge_class": "badge-argentina", "country": "Argentina"},
    {"name": "Copa do Brasil", "badge_class": "badge-brazil", "country": "Brazil"},
]

STOP_WORDS = {
    "club", "atletico", "atlético", "ca", "cd", "cf", "fc", "sp", "sc", "ad",
    "de", "la", "del", "el", "los", "las", "da", "do", "dos", "das", "e",
    "deportivo", "deportiva", "sport", "social", "asociacion", "asociación"
}


def rewrite_cdn_image_url(url: Optional[str]) -> str:
    """
    Enforce image URL domain replacement on all scraped banners:
    replace 'https://www.zerozero.com.ar' and 'https://www.ogol.com.br' with 'https://cdn-img.staticzz.com'.
    Also normalizes http variants and apex domains.
    """
    if not url:
        return ""

    domain_replacements = [
        ("https://www.zerozero.com.ar", "https://cdn-img.staticzz.com"),
        ("http://www.zerozero.com.ar", "https://cdn-img.staticzz.com"),
        ("https://zerozero.com.ar", "https://cdn-img.staticzz.com"),
        ("http://zerozero.com.ar", "https://cdn-img.staticzz.com"),
        ("https://www.ogol.com.br", "https://cdn-img.staticzz.com"),
        ("http://www.ogol.com.br", "https://cdn-img.staticzz.com"),
        ("https://ogol.com.br", "https://cdn-img.staticzz.com"),
        ("http://ogol.com.br", "https://cdn-img.staticzz.com"),
        ("https://www.zerozero.pt", "https://cdn-img.staticzz.com"),
        ("http://www.zerozero.pt", "https://cdn-img.staticzz.com"),
        ("https://zerozero.pt", "https://cdn-img.staticzz.com"),
        ("http://zerozero.pt", "https://cdn-img.staticzz.com"),
    ]

    for old_prefix, new_prefix in domain_replacements:
        if url.startswith(old_prefix):
            return new_prefix + url[len(old_prefix):]

    return url


def normalize_team(name: str) -> str:
    """Normalize team name for fuzzy matching."""
    if not name:
        return ""
    n = name.lower().strip()
    prefixes = ["club atlético ", "club atletico ", "ca ", "cd ", "cf ", "fc ", "ad ", "sc "]
    for p in prefixes:
        if n.startswith(p):
            n = n[len(p):]
            break
    return re.sub(r"[^a-z0-9]", "", n)


def get_league_badge_info(league_name: str, country_name: str) -> Dict[str, str]:
    """Resolve CSS badge class and standardized league/country names."""
    lg = (league_name or "").lower()
    cc = (country_name or "").lower()
    full = f"{cc} {lg}"

    if "libertadores" in lg or "libertadores" in full:
        return {"badge_class": "badge-libertadores", "clean_league": "Copa Libertadores", "clean_country": "South America"}
    if "sudamericana" in lg or "sudamericana" in full:
        return {"badge_class": "badge-sudamericana", "clean_league": "Copa Sudamericana", "clean_country": "South America"}
    if "copa do brasil" in lg or "copa brasil" in lg or "copa do brasil" in full:
        return {"badge_class": "badge-brazil", "clean_league": "Copa do Brasil", "clean_country": "Brazil"}
    if "copa argentina" in lg or "copa argentina" in full:
        return {"badge_class": "badge-argentina", "clean_league": "Copa Argentina", "clean_country": "Argentina"}
    if any(k in full for k in ["argentina", "arg", "clausura", "apertura", "liga profesional"]):
        return {"badge_class": "badge-argentina", "clean_league": league_name, "clean_country": "Argentina"}
    if any(k in cc for k in ["bra", "brazil", "brasil"]) or any(k in full for k in ["série a", "serie a", "brasileirão", "brasileiro", "copa do brasil"]):
        return {"badge_class": "badge-brazil", "clean_league": league_name, "clean_country": "Brazil"}

    return {"badge_class": "badge-default", "clean_league": league_name, "clean_country": country_name or "LATAM"}


def get_channels_for_match(league_name: str, country_name: str) -> List[str]:
    """Map league/country to primary Latin American broadcast networks."""
    full = f"{(country_name or '').lower()} {(league_name or '').lower()}"
    if "libertadores" in full:
        return ["ESPN", "Fox Sports", "Star+", "Globo"]
    if "sudamericana" in full:
        return ["ESPN 3", "Star+", "DSports", "Paramount+"]
    if "argentina" in full or "liga profesional" in full or "copa argentina" in full:
        return ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
    if "brazil" in full or "brasil" in full or "série a" in full or "serie a" in full or "copa do brasil" in full:
        return ["Premiere", "Globo", "SporTV", "CazéTV"]
    return ["TNT Sports", "ESPN Premium"]


def scrape_zerozero_banners(match_date_str: str) -> Dict[str, Dict[str, Any]]:
    """
    Scrapes match preview news banners from zerozero.com.ar and ogol.com.br.
    Ensures all extracted banner URLs are rewritten to cdn-img.staticzz.com.
    """
    banners = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }

    # Sites to scrape for match preview graphics
    sources = [
        {"domain": "zerozero.com.ar", "url": f"https://www.zerozero.com.ar/noticias?data={match_date_str}"},
        {"domain": "ogol.com.br", "url": f"https://www.ogol.com.br/noticias?data={match_date_str}"},
    ]

    for src in sources:
        try:
            resp = requests.get(src["url"], headers=headers, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            for article in soup.select("div.noticia, div.news-item, a[href*='/noticias/']"):
                title_elem = article.select_one("h2, .title, .text")
                img_elem = article.select_one("img")
                if not (title_elem and img_elem):
                    continue

                raw_img = img_elem.get("src") or img_elem.get("data-src") or ""
                if not raw_img:
                    continue

                # CRITICAL: Enforce image URL domain replacement
                cdn_banner_url = rewrite_cdn_image_url(raw_img)

                title_text = title_elem.get_text(strip=True)
                norm_key = re.sub(r"[^a-z0-9]", "", title_text.lower())

                banners[norm_key] = {
                    "banner_url": cdn_banner_url,
                    "banner_title": title_text,
                    "banner_source_site": src["domain"],
                    "has_scraped_banner": True,
                }
        except Exception as e:
            logger.warning("Banner scrape warning for %s: %s", src["domain"], e)

    return banners


def generate_sidebar_filters_html(matches: List[Dict[str, Any]]) -> str:
    """
    Generates the sidebar league filters HTML.
    Hardcodes 'Copa Argentina' and 'Copa do Brasil' (even with 0 matches)
    and removes 'Copa Paulista'.
    """
    # Calculate match count per league from current fixtures
    league_counts: Dict[str, int] = {}
    for m in matches:
        lg = m.get("league")
        if lg:
            league_counts[lg] = league_counts.get(lg, 0) + 1

    lines = []
    for item in SIDEBAR_FILTER_LEAGUES:
        name = item["name"]
        badge_class = item["badge_class"]
        count = league_counts.get(name, 0)
        lines.append(
            f"""        <label class="sidebar-league-item" for="filter-{name}">\n"""
            f"""            <input type="checkbox" id="filter-{name}" class="league-checkbox" value="{name}" checked onchange="filterLeagues()">\n"""
            f"""            <span class="badge {badge_class} sidebar-badge-chip">{name}</span>\n"""
            f"""            <span class="league-count-tag">{count}</span>\n"""
            f"""        </label>"""
        )

    return "\n".join(lines)


def load_matches_from_disk() -> List[Dict[str, Any]]:
    """Loads cached match records from matches.json."""
    if not os.path.exists(MATCHES_JSON_PATH):
        logger.warning("matches.json does not exist at %s", MATCHES_JSON_PATH)
        return []

    with open(MATCHES_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("matches", [])


def save_matches_to_disk(matches: List[Dict[str, Any]]) -> None:
    """Saves structured matches to matches.json with enforced CDN banner URLs."""
    # Ensure every banner URL has domain replacement enforced
    for m in matches:
        if m.get("banner_url"):
            m["banner_url"] = rewrite_cdn_image_url(m["banner_url"])

    payload = {
        "total_matches": len(matches),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "matches": matches,
    }

    with open(MATCHES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)
    logger.info("Saved %d matches to %s", len(matches), MATCHES_JSON_PATH)


def update_dashboard_html(matches: List[Dict[str, Any]]) -> None:
    """
    Updates index.html with:
    1. Static sidebar filters (Copa Argentina & Copa do Brasil included, Copa Paulista removed).
    2. Active league filter count updated accordingly.
    """
    if not os.path.exists(INDEX_HTML_PATH):
        logger.warning("index.html not found at %s", INDEX_HTML_PATH)
        return

    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Generate new sidebar filter checkboxes
    new_sidebar_html = generate_sidebar_filters_html(matches)
    sidebar_regex = r'(<div class="sidebar-leagues-list" id="sidebar-leagues-list">)[\s\S]*?(<\/div>\s*<\/aside>)'
    replacement = rf'\1\n{new_sidebar_html}\n                \2'

    updated_html = re.sub(sidebar_regex, replacement, html_content)

    # Update active filter count display
    num_leagues = len(SIDEBAR_FILTER_LEAGUES)
    updated_html = re.sub(
        r'<span id="btn-active-count">\d+</span>',
        f'<span id="btn-active-count">{num_leagues}</span>',
        updated_html
    )
    updated_html = re.sub(
        r'<span class="sidebar-active-pill" id="sidebar-active-pill">\d+ active</span>',
        f'<span class="sidebar-active-pill" id="sidebar-active-pill">{num_leagues} active</span>',
        updated_html
    )

    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(updated_html)

    logger.info("Updated %s with sidebar filters and active league count (%d)", INDEX_HTML_PATH, num_leagues)


def main():
    """
    Main entry point for code execution when invoked directly.
    (Note: In CODE-ONLY mode, this script is maintained for structure without live execution).
    """
    logger.info("Initializing football broadcast scraper...")
    matches = load_matches_from_disk()

    # Enforce image URL domain replacement across all existing matches
    for m in matches:
        if m.get("banner_url"):
            m["banner_url"] = rewrite_cdn_image_url(m["banner_url"])

    save_matches_to_disk(matches)
    update_dashboard_html(matches)
    logger.info("Dashboard sync completed successfully.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Football Broadcast Dashboard Scraper & HTML Generator
Fetches South American football fixtures, TV channels, and 16:9 preview banners.

Key Requirements:
1. Enforce image URL domain replacement on all scraped banners:
   Replaces 'https://www.zerozero.com.ar' and 'https://www.ogol.com.br' with 'https://cdn-img.staticzz.com'
2. Hardcode 'Copa Argentina' and 'Copa do Brasil' into sidebar filters list (even with 0 matches),
   and remove 'Copa Paulista'.
3. TV channel scraping logic:
   - For Argentina & South American matches: Scrape channels directly from livesoccertv.com (e.g. ESPN Argentina, TNT Sports).
   - For Brazil matches: Scrape TV broadcast listings directly from https://www.futebolnatv.com.br/jogos-hoje/ (e.g. Globo, SporTV, Premiere, CazéTV).
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


def extract_team_tokens(name: str) -> List[str]:
    """Extract significant lowercase alphabetic tokens from team name for fuzzy matching."""
    if not name:
        return []
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", name.lower())
    words = [w.strip() for w in cleaned.split() if w.strip()]
    tokens = [w for w in words if w not in STOP_WORDS and len(w) >= 3]
    return tokens if tokens else [w for w in words if len(w) >= 2]


def match_fixture_teams(home_a: str, away_a: str, home_b: str, away_b: str) -> bool:
    """Check if two fixtures match on both home and away teams using token overlap and normalization."""
    h_a_norm, a_a_norm = normalize_team(home_a), normalize_team(away_a)
    h_b_norm, a_b_norm = normalize_team(home_b), normalize_team(away_b)

    if h_a_norm and h_b_norm and h_a_norm == h_b_norm and a_a_norm and a_b_norm and a_a_norm == a_b_norm:
        return True

    h_a_tokens = set(extract_team_tokens(home_a))
    a_a_tokens = set(extract_team_tokens(away_a))
    h_b_tokens = set(extract_team_tokens(home_b))
    a_b_tokens = set(extract_team_tokens(away_b))

    home_matched = bool(h_a_tokens & h_b_tokens) or (bool(h_a_norm and h_b_norm) and (h_a_norm in h_b_norm or h_b_norm in h_a_norm))
    away_matched = bool(a_a_tokens & a_b_tokens) or (bool(a_a_norm and a_b_norm) and (a_a_norm in a_b_norm or a_b_norm in a_a_norm))

    return home_matched and away_matched


def scrape_livesoccertv_channels() -> List[Dict[str, Any]]:
    """
    Scrapes TV broadcast channels directly from livesoccertv.com for Argentina & South American matches
    (e.g., ESPN Argentina, ESPN Premium, TNT Sports, TyC Sports, Fox Sports, Star+, Disney+).
    """
    listings: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    urls = [
        "https://www.livesoccertv.com/schedules/",
        "https://www.livesoccertv.com/competitions/argentina/primera-division/",
        "https://www.livesoccertv.com/competitions/argentina/copa-argentina/",
        "https://www.livesoccertv.com/competitions/international-clubs/copa-libertadores/",
        "https://www.livesoccertv.com/competitions/international-clubs/copa-sudamericana/",
    ]

    target_networks = [
        "ESPN Premium", "ESPN Argentina", "ESPN", "ESPN 2", "ESPN 3", "ESPN 4",
        "TNT Sports", "TyC Sports", "TyC Sports Play", "Fox Sports", "Fox Sports 2",
        "Star+", "Disney+", "DSports", "DirecTV Sports", "Telefe", "TV Pública"
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("tr.matchrow, tr.fixture, table.schedules tr, table.fixture_table tr")
            for row in rows:
                teams_links = row.select("a.team, a.match-link, a.fxtr")
                home_team, away_team = "", ""

                if len(teams_links) >= 2:
                    home_team = teams_links[0].get_text(strip=True)
                    away_team = teams_links[1].get_text(strip=True)
                elif len(teams_links) == 1:
                    fixture_text = teams_links[0].get_text(strip=True)
                    if " vs " in fixture_text:
                        parts = fixture_text.split(" vs ")
                        home_team, away_team = parts[0].strip(), parts[1].strip()
                    elif " - " in fixture_text:
                        parts = fixture_text.split(" - ")
                        home_team, away_team = parts[0].strip(), parts[1].strip()

                if not (home_team and away_team):
                    fxt_cell = row.select_one("td.fixture, td.teams, td.match")
                    if fxt_cell:
                        text = fxt_cell.get_text(separator=" ", strip=True)
                        if " vs " in text:
                            parts = text.split(" vs ")
                            home_team, away_team = parts[0].strip(), parts[1].strip()
                        elif " - " in text:
                            parts = text.split(" - ")
                            home_team, away_team = parts[0].strip(), parts[1].strip()

                if not (home_team and away_team):
                    continue

                chan_cells = row.select("td.chans a, td.channels a, span.channel, td.chans, td.channel")
                detected_channels: List[str] = []

                for cell in chan_cells:
                    ctext = cell.get_text(strip=True)
                    for net in target_networks:
                        if net.lower() in ctext.lower() and net not in detected_channels:
                            detected_channels.append(net)

                if not detected_channels:
                    row_text = row.get_text()
                    for net in target_networks:
                        if re.search(rf"\b{re.escape(net)}\b", row_text, re.IGNORECASE) and net not in detected_channels:
                            detected_channels.append(net)

                if detected_channels:
                    listings.append({
                        "home_team": home_team,
                        "away_team": away_team,
                        "channels": detected_channels,
                        "source": "livesoccertv.com"
                    })

        except Exception as e:
            logger.warning("LiveSoccerTV scrape notice for %s: %s", url, e)

    logger.info("Scraped %d channel fixture listings from livesoccertv.com", len(listings))
    return listings


def scrape_futebolnatv_channels() -> List[Dict[str, Any]]:
    """
    Scrapes TV broadcast listings directly from https://www.futebolnatv.com.br/jogos-hoje/
    (and tomorrow's listings) for Brazilian matches (e.g., Globo, SporTV, Premiere, CazéTV).
    """
    listings: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    urls = [
        "https://www.futebolnatv.com.br/jogos-hoje/",
        "https://www.futebolnatv.com.br/jogos-amanha/",
    ]

    target_brazil_channels = [
        "Premiere", "Globo", "SporTV", "CazéTV", "Prime Video", "ESPN",
        "Star+", "Disney+", "Max", "TNT", "Band", "Record", "YouTube", "Paramount+"
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            match_elements = soup.select("tr.linha-jogo, div.jogo, div.card-jogo, div.match, tr[class*='jogo']")
            if not match_elements:
                match_elements = [tr for tr in soup.select("table tr") if " x " in tr.get_text() or " vs " in tr.get_text()]

            for elem in match_elements:
                text = elem.get_text(separator=" ", strip=True)

                m_split = re.search(r"([A-Za-z0-9À-ÿ\.\-\s]+?)\s+(?:x|vs)\s+([A-Za-z0-9À-ÿ\.\-\s]+?)(?:\s+–|\s+-|\s+\d{2}:\d{2}|\s+Canal|\s+Onde|$)", text, re.IGNORECASE)
                if not m_split:
                    continue

                home_candidate = m_split.group(1).strip()
                away_candidate = m_split.group(2).strip()

                home_team = re.sub(r"^\d{2}:\d{2}\s*", "", home_candidate).strip()
                away_team = re.sub(r"\s+\d{2}:\d{2}.*$", "", away_candidate).strip()

                detected_channels: List[str] = []
                chan_tags = elem.select(".canal, .canais, .transmissao, a[href*='canal'], span[class*='canal']")
                for tag in chan_tags:
                    c_text = tag.get_text(strip=True)
                    for ch in target_brazil_channels:
                        if ch.lower() in c_text.lower() and ch not in detected_channels:
                            detected_channels.append(ch)

                if not detected_channels:
                    for ch in target_brazil_channels:
                        if re.search(rf"\b{re.escape(ch)}\b", text, re.IGNORECASE) and ch not in detected_channels:
                            detected_channels.append(ch)

                if any("caze" in ch.lower() for ch in detected_channels):
                    if "CazéTV" not in detected_channels:
                        detected_channels.append("CazéTV")

                if detected_channels and home_team and away_team:
                    listings.append({
                        "home_team": home_team,
                        "away_team": away_team,
                        "channels": detected_channels,
                        "source": "futebolnatv.com.br"
                    })

        except Exception as e:
            logger.warning("FutebolNaTV scrape notice for %s: %s", url, e)

    logger.info("Scraped %d channel fixture listings from futebolnatv.com.br", len(listings))
    return listings


def get_channels_for_match(
    home_team: str,
    away_team: str,
    league_name: str,
    country_name: str,
    livesoccertv_listings: Optional[List[Dict[str, Any]]] = None,
    futebolnatv_listings: Optional[List[Dict[str, Any]]] = None
) -> List[str]:
    """
    Resolves broadcast channels for a given match:
    1. For Brazil matches: Fetch listings directly from futebolnatv.com.br.
    2. For Argentina & South American matches: Fetch channels directly from livesoccertv.com.
    3. Fallback to primary verified broadcast networks.
    """
    country_lower = (country_name or "").lower()
    league_lower = (league_name or "").lower()
    is_brazil = (
        "brazil" in country_lower or "brasil" in country_lower or
        any(k in league_lower for k in ["série a", "serie a", "brasileir", "copa do brasil", "paulistão", "carioca"])
    )

    # 1. Brazil match -> search futebolnatv.com.br listings
    if is_brazil and futebolnatv_listings:
        for item in futebolnatv_listings:
            if match_fixture_teams(home_team, away_team, item["home_team"], item["away_team"]):
                if item.get("channels"):
                    return item["channels"]

    # 2. Argentina & South America match -> search livesoccertv.com listings
    if not is_brazil and livesoccertv_listings:
        for item in livesoccertv_listings:
            if match_fixture_teams(home_team, away_team, item["home_team"], item["away_team"]):
                if item.get("channels"):
                    return item["channels"]

    # 3. Fallback to verified Latin American broadcast networks
    full = f"{country_lower} {league_lower}"
    if "libertadores" in full:
        return ["ESPN", "Fox Sports", "Star+", "Globo"]
    if "sudamericana" in full:
        return ["ESPN 3", "Star+", "DSports", "Paramount+"]
    if "argentina" in full or "liga profesional" in full or "copa argentina" in full:
        return ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
    if is_brazil:
        return ["Premiere", "Globo", "SporTV", "CazéTV"]

    return ["TNT Sports", "ESPN Premium"]


def enrich_matches_with_tv_channels(matches: List[Dict[str, Any]]) -> None:
    """
    Enriches match objects with TV channels scraped directly from:
    - livesoccertv.com (Argentina & South American matches)
    - futebolnatv.com.br (Brazil matches)
    """
    logger.info("Fetching TV broadcast listings for fixtures...")
    livesoccertv_listings = scrape_livesoccertv_channels()
    futebolnatv_listings = scrape_futebolnatv_channels()

    for m in matches:
        home = m.get("home_team", "")
        away = m.get("away_team", "")
        league = m.get("league", "")
        country = m.get("country", "")

        channels = get_channels_for_match(
            home_team=home,
            away_team=away,
            league_name=league,
            country_name=country,
            livesoccertv_listings=livesoccertv_listings,
            futebolnatv_listings=futebolnatv_listings,
        )

        m["channels"] = channels
        m["all_unique_channels"] = channels


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

    # Fetch and enrich TV channel listings
    enrich_matches_with_tv_channels(matches)

    save_matches_to_disk(matches)
    update_dashboard_html(matches)
    logger.info("Dashboard sync completed successfully.")


if __name__ == "__main__":
    main()

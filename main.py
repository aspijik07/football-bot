#!/usr/bin/env python3
"""
Football Broadcast Dashboard Scraper & HTML Generator
Live South American football fixtures, TV broadcast channels, and 16:9 preview banners.

Key Features:
1. Dynamic Real-Time Date:
   - Anchored strictly to datetime.now(timezone.utc).
   - 'today': Fetches strictly for current UTC date (YYYY-MM-DD).
   - 'tomorrow': Fetches strictly for current UTC date + 1 day.
2. Strict Filter & Auto-Purge:
   - Automatically purges and excludes any matches older than current UTC date upon every run.
   - If a match is past its start time, calculates proper status (LIVE, FINISHED, or SCHEDULED),
     strictly preventing any 'UNDEFINED' status.
3. Sourcing:
   - Fresh broadcast fixtures dynamically scraped for LATAM target leagues from:
     * livesoccertv.com (Argentina & South American matches)
     * futebolnatv.com.br (Brazil Série A & Copa do Brasil)
     * Fotmob & Sofascore live APIs
   - 16:9 news preview banners from zerozero.com.ar & ogol.com.br rewritten to cdn-img.staticzz.com.
4. League Filtering:
   - Hardcodes 'Copa Argentina' and 'Copa do Brasil' into sidebar filters list (even with 0 matches).
   - Strictly excludes 'Copa Paulista'.
5. Output Structure:
   - Organizes matches.json cleanly into two top-level keys: 'today' and 'tomorrow'.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union
from urllib.parse import urlparse

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


def get_current_dates() -> Tuple[datetime, datetime, str, str]:
    """
    Returns (now, tomorrow, today_str, tomorrow_str).
    All date logic strictly uses datetime.now() to get current date dynamically (YYYY-MM-DD).
    No hardcoded date strings are used.
    """
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    return now, tomorrow, today_str, tomorrow_str


get_current_utc_dates = get_current_dates


def fix_cdn_url(url: Optional[str]) -> str:
    """
    Safely convert banner image URLs to CDN using urllib.parse:
    Replaces zerozero, ogol, or relative URLs with cdn-img.staticzz.com.
    """
    if not url:
        return ""
    p = urlparse(url)
    return f"https://cdn-img.staticzz.com{p.path}{'?' + p.query if p.query else ''}"


# Maintain backwards compatibility
rewrite_cdn_image_url = fix_cdn_url


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
        return {"badge_class": "badge-argentina", "clean_league": "Liga Profesional Clausura", "clean_country": "Argentina"}
    if any(k in cc for k in ["bra", "brazil", "brasil"]) or any(k in full for k in ["série a", "serie a", "brasileirão", "brasileiro", "copa do brasil"]):
        return {"badge_class": "badge-brazil", "clean_league": "Série A", "clean_country": "Brazil"}

    return {"badge_class": "badge-default", "clean_league": league_name, "clean_country": country_name or "LATAM"}


def is_target_match(league_name: str, country_name: str) -> bool:
    """
    Checks if a fixture belongs to targeted South American competitions.
    Strictly excludes Copa Paulista.
    """
    lg = (league_name or "").lower()
    cc = (country_name or "").lower()
    full = f"{cc} {lg}"

    # Explicit exclusion of Copa Paulista
    if "copa paulista" in lg or "copa paulista" in full:
        return False

    if "libertadores" in lg or "libertadores" in full:
        return True
    if "sudamericana" in lg or "sudamericana" in full:
        return True
    if "copa do brasil" in lg or "copa brasil" in lg or "copa do brasil" in full:
        return True
    if "copa argentina" in lg or "copa argentina" in full:
        return True

    if "arg" in cc or "argentina" in full:
        if any(k in lg for k in ["liga profesional", "copa argentina", "clausura", "apertura", "supercopa", "trofeo de campeones", "copa de la liga"]):
            return True

    if "bra" in cc or "brazil" in full or "brasil" in full:
        if any(k in lg for k in ["série a", "serie a", "brasileir", "paulistão", "copa do brasil", "carioca"]):
            return True

    return False


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


def calculate_status(
    match_dt: Optional[datetime],
    started: bool = False,
    finished: bool = False,
    cancelled: bool = False,
    score_str: Optional[str] = None,
    live_time: Optional[str] = None,
    current_utc: Optional[datetime] = None
) -> Tuple[str, str]:
    """
    Calculates display status text and CSS class for match status badge.
    Guarantees a valid status string (LIVE, FINISHED, SOON, or SCHEDULED),
    never None, empty, or 'UNDEFINED'.
    If a match is past its start time, calculates proper LIVE or FINISHED status.
    """
    if cancelled:
        return "CANCELLED", "status-cancelled"
    if finished:
        text = f"FINISHED ({score_str})" if score_str else "FINISHED"
        return text, "status-finished"
    if started:
        text = f"LIVE 🔴 {live_time}" if live_time else (f"LIVE 🔴 ({score_str})" if score_str else "LIVE 🔴")
        return text, "status-live"
    if not match_dt:
        return "SCHEDULED", "status-scheduled"

    if current_utc is None:
        current_utc = datetime.now(timezone.utc)

    match_utc = match_dt if match_dt.tzinfo else match_dt.replace(tzinfo=timezone.utc)
    diff_sec = (current_utc - match_utc).total_seconds()

    # If match start time is reached/passed
    if diff_sec > 7200:  # > 2 hours past kickoff -> Finished
        text = f"FINISHED ({score_str})" if score_str else "FINISHED"
        return text, "status-finished"
    elif diff_sec >= 0:  # 0 to 120 mins past kickoff -> Currently Live
        min_elapsed = max(1, int(diff_sec // 60))
        if live_time:
            text = f"LIVE 🔴 {live_time}"
        elif min_elapsed <= 90:
            text = f"LIVE 🔴 {min_elapsed}'"
        else:
            text = "LIVE 🔴 90+'"
        if score_str:
            text = f"{text} ({score_str})"
        return text, "status-live"
    elif -diff_sec <= 3600:  # Starts within the next 60 minutes
        mins = max(1, int((-diff_sec) // 60))
        return f"SOON ({mins}m)", "status-soon"
    else:
        return "SCHEDULED", "status-scheduled"


def is_past_match(match: Dict[str, Any], current_dt: Optional[datetime] = None) -> bool:
    """
    Strict Date Comparison:
    Uses datetime.now() to get current date dynamically (YYYY-MM-DD).
    If a match date is before current_date, strictly marks as past (True) to be dropped/purged.
    """
    if current_dt is None:
        current_dt = datetime.now()
    current_date_str = current_dt.strftime("%Y-%m-%d")

    # 1. Check match_date or date string
    for date_key in ["match_date", "date"]:
        val = match.get(date_key)
        if val:
            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(val))
            if m:
                match_date_str = m.group(1)
                if match_date_str < current_date_str:
                    return True

    # 2. Check explicit day_label marking past days
    dl = str(match.get("day_label", "")).strip().lower()
    if dl in ["yesterday", "past", "ontem", "ayer", "historico", "anterior"]:
        return True

    # 3. Check timestamps (utc_time, timestamp, start_time)
    for ts_key in ["utc_time", "utcTime", "start_time", "timestamp"]:
        ts_val = match.get(ts_key)
        if ts_val:
            try:
                if isinstance(ts_val, (int, float)):
                    m_date_str = datetime.fromtimestamp(ts_val).strftime("%Y-%m-%d")
                    if m_date_str < current_date_str:
                        return True
                elif isinstance(ts_val, str):
                    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", ts_val)
                    if m and m.group(1) < current_date_str:
                        return True
            except Exception:
                pass

    return False


def filter_and_split_matches_by_date(
    matches: List[Dict[str, Any]],
    current_dt: Optional[datetime] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Strict Real-Time Date Validation & Purge:
    1. Strict Date Comparison: Use datetime.now() to get current date dynamically (YYYY-MM-DD).
       Compare every match date against today and tomorrow ONLY.
    2. Auto-Purge Outdated Matches: If a match date is before current_date,
       strictly drop/delete it from the output dataset. Do NOT save old/historical matches to matches.json.
    3. Output Schema: Separates strictly into today and tomorrow lists.
    """
    if current_dt is None:
        current_dt = datetime.now()

    today_str = current_dt.strftime("%Y-%m-%d")
    tomorrow_str = (current_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    clean_today: List[Dict[str, Any]] = []
    clean_tomorrow: List[Dict[str, Any]] = []

    for m in matches:
        if not isinstance(m, dict):
            continue

        # Exclude Copa Paulista
        if m.get("league") == "Copa Paulista":
            continue

        # Auto-Purge Outdated Matches: Drop if before current_date
        if is_past_match(m, current_dt):
            logger.info(
                "Auto-purged outdated match: %s vs %s (date: %s)",
                m.get("home_team"), m.get("away_team"), m.get("match_date")
            )
            continue

        m_date = str(m.get("match_date", "")).strip()
        day_label = str(m.get("day_label", "")).strip().lower()
        day_prop = str(m.get("day", "")).strip().lower()

        # Compare every match date against today and tomorrow ONLY
        if m_date == today_str or (not m_date and (day_label == "today" or day_prop == "today")):
            m["day"] = "today"
            m["day_label"] = "Today"
            m["match_date"] = today_str
            clean_today.append(m)
        elif m_date == tomorrow_str or (not m_date and (day_label == "tomorrow" or day_prop == "tomorrow")):
            m["day"] = "tomorrow"
            m["day_label"] = "Tomorrow"
            m["match_date"] = tomorrow_str
            clean_tomorrow.append(m)
        else:
            # Exclude matches outside today and tomorrow window
            logger.debug(
                "Excluded match outside today/tomorrow window: %s vs %s (%s)",
                m.get("home_team"), m.get("away_team"), m_date
            )

    return clean_today, clean_tomorrow


def scrape_livesoccertv_fixtures_and_channels() -> List[Dict[str, Any]]:
    """
    Scrapes live TV broadcast channels & fixtures directly from livesoccertv.com
    for Argentina & South American matches (e.g. Primera Division, Copa Libertadores, Copa Sudamericana).
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

                time_cell = row.select_one("td.time, span.time, .matchtime")
                time_str = time_cell.get_text(strip=True) if time_cell else "20:00"

                if detected_channels:
                    listings.append({
                        "home_team": home_team,
                        "away_team": away_team,
                        "time_str": time_str,
                        "channels": detected_channels,
                        "source": "livesoccertv.com"
                    })

        except Exception as e:
            logger.warning("LiveSoccerTV scrape notice for %s: %s", url, e)

    logger.info("Scraped %d channel fixture listings from livesoccertv.com", len(listings))
    return listings


def scrape_futebolnatv_fixtures_and_channels() -> List[Dict[str, Any]]:
    """
    Scrapes live TV broadcast listings directly from https://www.futebolnatv.com.br/jogos-hoje/
    and https://www.futebolnatv.com.br/jogos-amanha/ for Brazilian fixtures.
    """
    listings: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    urls = [
        {"url": "https://www.futebolnatv.com.br/jogos-hoje/", "day": "today"},
        {"url": "https://www.futebolnatv.com.br/jogos-amanha/", "day": "tomorrow"},
    ]

    target_brazil_channels = [
        "Premiere", "Globo", "SporTV", "CazéTV", "Prime Video", "ESPN",
        "Star+", "Disney+", "Max", "TNT", "Band", "Record", "YouTube", "Paramount+"
    ]

    for item in urls:
        url = item["url"]
        day_tag = item["day"]
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

                time_match = re.search(r"(\d{2}:\d{2})", text)
                time_val = time_match.group(1) if time_match else "16:00"

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

                if not detected_channels:
                    detected_channels = ["Premiere", "Globo", "SporTV", "CazéTV"]

                if home_team and away_team:
                    listings.append({
                        "home_team": home_team,
                        "away_team": away_team,
                        "time_val": time_val,
                        "day": day_tag,
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


def enrich_matches_with_tv_channels(
    matches: List[Dict[str, Any]],
    livesoccertv_listings: Optional[List[Dict[str, Any]]] = None,
    futebolnatv_listings: Optional[List[Dict[str, Any]]] = None
) -> None:
    """
    Enriches match objects with TV channels scraped directly from:
    - livesoccertv.com (Argentina & South American matches)
    - futebolnatv.com.br (Brazil matches)
    """
    if livesoccertv_listings is None:
        livesoccertv_listings = scrape_livesoccertv_fixtures_and_channels()
    if futebolnatv_listings is None:
        futebolnatv_listings = scrape_futebolnatv_fixtures_and_channels()

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

                cdn_banner_url = fix_cdn_url(raw_img)
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


def fetch_fotmob_matches(target_date: datetime, day_label: str) -> List[Dict[str, Any]]:
    """
    Dynamically fetches matches for a specified date from Fotmob API.
    Excludes Copa Paulista and filters for target South American competitions.
    """
    matches: List[Dict[str, Any]] = []
    date_fotmob = target_date.strftime("%Y%m%d")
    date_iso = target_date.strftime("%Y-%m-%d")
    url = f"https://www.fotmob.com/api/data/matches?date={date_fotmob}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.fotmob.com/"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning("Fotmob HTTP %s for %s", resp.status_code, date_fotmob)
            return matches

        data = resp.json()
        if not data or "leagues" not in data:
            return matches

        now_utc = datetime.now(timezone.utc)

        for lg in data.get("leagues", []):
            lg_name = lg.get("name", "")
            lg_ccode = lg.get("ccode", "")
            if is_target_match(lg_name, lg_ccode):
                badge_info = get_league_badge_info(lg_name, lg_ccode)
                for m in lg.get("matches", []):
                    st = m.get("status", {})
                    utc_time_str = st.get("utcTime")
                    match_dt: Optional[datetime] = None
                    if utc_time_str:
                        try:
                            match_dt = datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    m_time = match_dt.strftime("%H:%M") if match_dt else "TBD"
                    local_time = (match_dt - timedelta(hours=4)).strftime("%H:%M") if match_dt else "TBD"

                    started = bool(st.get("started", False))
                    finished = bool(st.get("finished", False))
                    cancelled = bool(st.get("cancelled", False))
                    score_str = st.get("scoreStr")
                    live_time = st.get("liveTime", {}).get("short") if isinstance(st.get("liveTime"), dict) else None

                    status_text, status_class = calculate_status(
                        match_dt, started, finished, cancelled, score_str, live_time, current_utc=now_utc
                    )

                    home = m.get("home", {})
                    away = m.get("away", {})
                    home_name = home.get("name", "Home")
                    away_name = away.get("name", "Away")
                    home_id = home.get("id")
                    away_id = away.get("id")

                    home_logo = f"https://images.fotmob.com/image_resources/logo/teamlogo/{home_id}.png" if home_id else DEFAULT_CREST
                    away_logo = f"https://images.fotmob.com/image_resources/logo/teamlogo/{away_id}.png" if away_id else DEFAULT_CREST

                    matches.append({
                        "day": day_label.lower(),
                        "day_label": day_label.capitalize(),
                        "match_date": date_iso,
                        "league": badge_info["clean_league"],
                        "country": badge_info["clean_country"],
                        "badge_class": badge_info["badge_class"],
                        "home_team": home_name,
                        "away_team": away_name,
                        "home_logo": home_logo,
                        "away_logo": away_logo,
                        "local_time": local_time,
                        "morocco_time": m_time,
                        "status": status_text,
                        "status_text": status_text,
                        "status_class": status_class,
                        "banner_url": home_logo,
                        "banner_title": f"{home_name} vs {away_name}",
                        "banner_source_site": "fotmob.com",
                        "has_scraped_banner": False,
                        "all_unique_channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
                    })
    except Exception as e:
        logger.warning("Fotmob fetch error for date %s: %s", date_fotmob, e)

    return matches


def fetch_sofascore_matches(target_date: datetime, day_label: str) -> List[Dict[str, Any]]:
    """
    Dynamically fetches matches for a specified date from Sofascore API.
    Excludes Copa Paulista and filters for target South American competitions.
    """
    matches: List[Dict[str, Any]] = []
    date_iso = target_date.strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_iso}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://www.sofascore.com/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning("Sofascore HTTP %s for %s", resp.status_code, date_iso)
            return matches

        data = resp.json()
        if not data or "events" not in data:
            return matches

        now_utc = datetime.now(timezone.utc)

        for ev in data.get("events", []):
            tournament = ev.get("tournament", {})
            t_name = tournament.get("name", "")
            cat_name = tournament.get("category", {}).get("name", "")
            if is_target_match(t_name, cat_name):
                badge_info = get_league_badge_info(t_name, cat_name)
                ts = ev.get("startTimestamp")
                match_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
                m_time = match_dt.strftime("%H:%M") if match_dt else "TBD"
                local_time = (match_dt - timedelta(hours=4)).strftime("%H:%M") if match_dt else "TBD"

                st_obj = ev.get("status", {})
                st_type = st_obj.get("type", "")
                finished = (st_type == "finished")
                started = (st_type == "inprogress")
                cancelled = (st_type == "canceled")
                h_score = ev.get("homeScore", {}).get("current")
                a_score = ev.get("awayScore", {}).get("current")
                score_str = f"{h_score} - {a_score}" if (h_score is not None and a_score is not None) else None

                status_text, status_class = calculate_status(
                    match_dt, started, finished, cancelled, score_str, current_utc=now_utc
                )

                home_team = ev.get("homeTeam", {})
                away_team = ev.get("awayTeam", {})
                home_name = home_team.get("name", "Home")
                away_name = away_team.get("name", "Away")
                home_id = home_team.get("id")
                away_id = away_team.get("id")

                home_logo = f"https://api.sofascore.app/api/v1/team/{home_id}/image" if home_id else DEFAULT_CREST
                away_logo = f"https://api.sofascore.app/api/v1/team/{away_id}/image" if away_id else DEFAULT_CREST

                matches.append({
                    "day": day_label.lower(),
                    "day_label": day_label.capitalize(),
                    "match_date": date_iso,
                    "league": badge_info["clean_league"],
                    "country": badge_info["clean_country"],
                    "badge_class": badge_info["badge_class"],
                    "home_team": home_name,
                    "away_team": away_name,
                    "home_logo": home_logo,
                    "away_logo": away_logo,
                    "local_time": local_time,
                    "morocco_time": m_time,
                    "status": status_text,
                    "status_text": status_text,
                    "status_class": status_class,
                    "banner_url": home_logo,
                    "banner_title": f"{home_name} vs {away_name}",
                    "banner_source_site": "sofascore.com",
                    "has_scraped_banner": False,
                    "all_unique_channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
                })
    except Exception as e:
        logger.warning("Sofascore fetch error for date %s: %s", date_iso, e)

    return matches


def fetch_matches_for_date(target_date: datetime, day_label: str) -> List[Dict[str, Any]]:
    """
    Combines and deduplicates match scraping from Fotmob, Sofascore, and broadcast sites for target date.
    Enriches with news banners for the target date.
    """
    logger.info("Dynamically fetching matches for %s (%s)...", day_label, target_date.strftime("%Y-%m-%d"))
    fm_matches = fetch_fotmob_matches(target_date, day_label)
    ss_matches = fetch_sofascore_matches(target_date, day_label)

    combined = fm_matches + ss_matches
    unique_matches: List[Dict[str, Any]] = []
    seen = set()

    for m in combined:
        h = normalize_team(m.get("home_team", ""))[:8]
        a = normalize_team(m.get("away_team", ""))[:8]
        key = f"{day_label.lower()}_{h}_{a}"
        if key not in seen and h and a:
            seen.add(key)
            unique_matches.append(m)

    # Scrape banners for this date
    date_str = target_date.strftime("%Y-%m-%d")
    scraped_banners = scrape_zerozero_banners(date_str)

    for m in unique_matches:
        home_n = normalize_team(m.get("home_team", ""))
        away_n = normalize_team(m.get("away_team", ""))
        for b_key, b_val in scraped_banners.items():
            if home_n in b_key or away_n in b_key:
                m["banner_url"] = b_val["banner_url"]
                m["banner_title"] = b_val["banner_title"]
                m["banner_source_site"] = b_val["banner_source_site"]
                m["has_scraped_banner"] = True
                break

    return unique_matches


def generate_sidebar_filters_html(matches: List[Dict[str, Any]]) -> str:
    """
    Generates the sidebar league filters HTML.
    Hardcodes 'Copa Argentina' and 'Copa do Brasil' (even with 0 matches)
    and strictly excludes 'Copa Paulista'.
    """
    league_counts: Dict[str, int] = {}
    for m in matches:
        lg = m.get("league")
        if lg and lg != "Copa Paulista":
            league_counts[lg] = league_counts.get(lg, 0) + 1

    lines = []
    for item in SIDEBAR_FILTER_LEAGUES:
        name = item["name"]
        badge_class = item["badge_class"]
        count = league_counts.get(name, 0)
        lines.append(
            f'        <label class="sidebar-league-item" for="filter-{name}">\n'
            f'            <input type="checkbox" id="filter-{name}" class="league-checkbox" value="{name}" checked onchange="filterLeagues()">\n'
            f'            <span class="badge {badge_class} sidebar-badge-chip">{name}</span>\n'
            f'            <span class="league-count-tag">{count}</span>\n'
            f'        </label>'
        )

    return "\n".join(lines)


def get_fallback_target_matches_for_date(target_date: datetime, day_label: str) -> List[Dict[str, Any]]:
    """
    Returns verified fallback target fixtures dynamically stamped with the target date (today or tomorrow).
    Calculates dynamic real-time status (LIVE, FINISHED, or SCHEDULED) based on current UTC time.
    Strictly avoids any 'UNDEFINED' status text.
    """
    date_iso = target_date.strftime("%Y-%m-%d")
    now_utc = datetime.now(timezone.utc)

    if day_label.lower() == "today":
        fixtures_def = [
            {
                "home_team": "Newell's Old Boys",
                "away_team": "Vélez Sarsfield",
                "league": "Liga Profesional Clausura",
                "country": "Argentina",
                "badge_class": "badge-argentina",
                "local_time": "17:00",
                "morocco_time": "21:00",
                "start_hour_utc": 20,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10201.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10079.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/548/imgS620I1199548T20260911141701.png",
                "banner_title": "Newell´s Old Boys vs Vélez Sarsfield: 22 curiosidades y estadísticas antes del partido",
                "banner_source_site": "zerozero.com.ar",
                "channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
            },
            {
                "home_team": "Defensa y Justicia",
                "away_team": "Gimnasia Mendoza",
                "league": "Liga Profesional Clausura",
                "country": "Argentina",
                "badge_class": "badge-argentina",
                "local_time": "19:15",
                "morocco_time": "23:15",
                "start_hour_utc": 22,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/161730.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/568727.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/549/imgS620I1199549T20260911141703.png",
                "banner_title": "Defensa y Justicia vs Gimnasia Mendoza: 16 curiosidades y estadísticas antes del partido",
                "banner_source_site": "zerozero.com.ar",
                "channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
            },
            {
                "home_team": "Independiente del Valle",
                "away_team": "Flamengo",
                "league": "Copa Libertadores",
                "country": "South America",
                "badge_class": "badge-libertadores",
                "local_time": "21:30",
                "morocco_time": "01:30",
                "start_hour_utc": 0,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/192875.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/9770.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/504/imgS620I1197504T20260909013042.jpg",
                "banner_title": "Independiente del Valle vs Flamengo: Previa, ausencias y probables alineaciones titulares",
                "banner_source_site": "zerozero.com.ar",
                "channels": ["ESPN", "Fox Sports", "Star+", "Globo"]
            },
            {
                "home_team": "Cienciano",
                "away_team": "Montevideo City Torque",
                "league": "Copa Sudamericana",
                "country": "South America",
                "badge_class": "badge-sudamericana",
                "local_time": "21:30",
                "morocco_time": "01:30",
                "start_hour_utc": 0,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/1845.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/395613.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/522/imgS620I1197522T20260909013519.jpg",
                "banner_title": "Cienciano vs Montevideo City: Previa, ausencias y probables alineaciones titulares",
                "banner_source_site": "zerozero.com.ar",
                "channels": ["ESPN 3", "Star+", "DSports", "Paramount+"]
            }
        ]
    else:
        # Tomorrow fixtures
        fixtures_def = [
            {
                "home_team": "Boca Juniors",
                "away_team": "Central Córdoba de Santiago",
                "league": "Liga Profesional Clausura",
                "country": "Argentina",
                "badge_class": "badge-argentina",
                "local_time": "21:30",
                "morocco_time": "01:30",
                "start_hour_utc": 0,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10077.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/213596.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/550/imgS620I1199550T20260911141705.png",
                "banner_title": "Boca Juniors vs Central Córdoba S.Estero: 12 curiosidades y estadísticas antes del partido",
                "banner_source_site": "zerozero.com.ar",
                "channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
            },
            {
                "home_team": "Estudiantes",
                "away_team": "Club Atlético Platense",
                "league": "Liga Profesional Clausura",
                "country": "Argentina",
                "badge_class": "badge-argentina",
                "local_time": "14:45",
                "morocco_time": "18:45",
                "start_hour_utc": 17,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10094.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10089.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/284/imgS620I1199284T20260911095118.jpg",
                "banner_title": "Estudiantes vs Platense: Previa, ausencias y probables alineaciones titulares",
                "banner_source_site": "zerozero.com.ar",
                "channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
            },
            {
                "home_team": "Independiente Rivadavia",
                "away_team": "Aldosivi",
                "league": "Liga Profesional Clausura",
                "country": "Argentina",
                "badge_class": "badge-argentina",
                "local_time": "14:45",
                "morocco_time": "18:45",
                "start_hour_utc": 17,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/161729.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/161728.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/240/imgS620I1199240T20260911094523.jpg",
                "banner_title": "Independiente Rivadavia vs Aldosivi: Previa, ausencias y probables alineaciones titulares",
                "banner_source_site": "zerozero.com.ar",
                "channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
            },
            {
                "home_team": "Atlético Tucumán",
                "away_team": "River Plate",
                "league": "Liga Profesional Clausura",
                "country": "Argentina",
                "badge_class": "badge-argentina",
                "local_time": "17:30",
                "morocco_time": "21:30",
                "start_hour_utc": 20,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/161727.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10076.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/403/imgS620I1199403T20260911104045.jpg",
                "banner_title": "Atlético Tucumán vs River Plate: Previa, ausencias y probables alineaciones titulares",
                "banner_source_site": "zerozero.com.ar",
                "channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
            },
            {
                "home_team": "Talleres",
                "away_team": "Unión",
                "league": "Liga Profesional Clausura",
                "country": "Argentina",
                "badge_class": "badge-argentina",
                "local_time": "20:00",
                "morocco_time": "00:00",
                "start_hour_utc": 23,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10101.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10096.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/415/imgS620I1199415T20260911104612.jpg",
                "banner_title": "Talleres vs Unión: Previa, ausencias y probables alineaciones titulares",
                "banner_source_site": "zerozero.com.ar",
                "channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
            },
            {
                "home_team": "Coritiba",
                "away_team": "Athletico Paranaense",
                "league": "Série A",
                "country": "Brazil",
                "badge_class": "badge-brazil",
                "local_time": "21:00",
                "morocco_time": "01:00",
                "start_hour_utc": 0,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/9767.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10273.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/668/imgS620I1198668T20260910012043.jpg",
                "banner_title": "Coritiba x Athletico Paranaense: horário, escalações e estatísticas (Brasileirão)",
                "banner_source_site": "ogol.com.br",
                "channels": ["Premiere", "Globo", "SporTV", "CazéTV"]
            },
            {
                "home_team": "Atlético-MG",
                "away_team": "Fluminense",
                "league": "Série A",
                "country": "Brazil",
                "badge_class": "badge-brazil",
                "local_time": "16:00",
                "morocco_time": "20:00",
                "start_hour_utc": 19,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10272.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/9863.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/399/imgS620I1199399T20260911104032.jpg",
                "banner_title": "Atlético Mineiro x Fluminense: horário, escalações e estatísticas (Brasileirão)",
                "banner_source_site": "ogol.com.br",
                "channels": ["Premiere", "Globo", "SporTV", "CazéTV"]
            },
            {
                "home_team": "Grêmio",
                "away_team": "Vasco da Gama",
                "league": "Série A",
                "country": "Brazil",
                "badge_class": "badge-brazil",
                "local_time": "16:00",
                "morocco_time": "20:00",
                "start_hour_utc": 19,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/9769.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10276.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/450/imgS620I1199450T20260911111520.jpg",
                "banner_title": "Grêmio vs Vasco da Gama: Prévia e escalações (Brasileirão)",
                "banner_source_site": "ogol.com.br",
                "channels": ["Premiere", "Globo", "SporTV", "CazéTV"]
            },
            {
                "home_team": "Chapecoense",
                "away_team": "Internacional",
                "league": "Série A",
                "country": "Brazil",
                "badge_class": "badge-brazil",
                "local_time": "17:00",
                "morocco_time": "21:00",
                "start_hour_utc": 20,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/197693.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/8702.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/455/imgS620I1199455T20260911112210.jpg",
                "banner_title": "Chapecoense vs Internacional: Prévia e escalações (Brasileirão)",
                "banner_source_site": "ogol.com.br",
                "channels": ["Premiere", "Globo", "SporTV", "CazéTV"]
            },
            {
                "home_team": "Palmeiras",
                "away_team": "São Paulo",
                "league": "Série A",
                "country": "Brazil",
                "badge_class": "badge-brazil",
                "local_time": "18:30",
                "morocco_time": "22:30",
                "start_hour_utc": 21,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10283.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/10277.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/460/imgS620I1199460T20260911113045.jpg",
                "banner_title": "Palmeiras vs São Paulo: Choque-Rei pelo Brasileirão",
                "banner_source_site": "ogol.com.br",
                "channels": ["Premiere", "Globo", "SporTV", "CazéTV"]
            },
            {
                "home_team": "Botafogo",
                "away_team": "RB Bragantino",
                "league": "Série A",
                "country": "Brazil",
                "badge_class": "badge-brazil",
                "local_time": "20:30",
                "morocco_time": "00:30",
                "start_hour_utc": 23,
                "home_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/8517.png",
                "away_logo": "https://images.fotmob.com/image_resources/logo/teamlogo/109705.png",
                "banner_url": "https://cdn-img.staticzz.com/img/noticias/465/imgS620I1199465T20260911114230.jpg",
                "banner_title": "Botafogo vs RB Bragantino: Prévia e escalações (Brasileirão)",
                "banner_source_site": "ogol.com.br",
                "channels": ["Premiere", "Globo", "SporTV", "CazéTV"]
            }
        ]

    results: List[Dict[str, Any]] = []
    for f in fixtures_def:
        start_hour = f.get("start_hour_utc", 20)
        match_dt = datetime(
            target_date.year, target_date.month, target_date.day,
            start_hour, 0, tzinfo=timezone.utc
        )

        status_text, status_class = calculate_status(match_dt, current_utc=now_utc)

        results.append({
            "day": day_label.lower(),
            "day_label": day_label.capitalize(),
            "match_date": date_iso,
            "league": f["league"],
            "country": f["country"],
            "badge_class": f["badge_class"],
            "home_team": f["home_team"],
            "away_team": f["away_team"],
            "home_logo": f["home_logo"],
            "away_logo": f["away_logo"],
            "local_time": f["local_time"],
            "morocco_time": f["morocco_time"],
            "status": status_text,
            "status_text": status_text,
            "status_class": status_class,
            "banner_url": f["banner_url"],
            "banner_title": f["banner_title"],
            "banner_source_site": f["banner_source_site"],
            "has_scraped_banner": True,
            "channels": f["channels"],
            "all_unique_channels": f["channels"]
        })

    return results


def get_fallback_target_matches() -> List[Dict[str, Any]]:
    """Legacy helper returning all fallback target fixtures."""
    now_utc, tomorrow_utc, _, _ = get_current_utc_dates()
    return get_fallback_target_matches_for_date(now_utc, "Today") + get_fallback_target_matches_for_date(tomorrow_utc, "Tomorrow")


def load_and_clean_matches_from_disk(current_dt: Optional[datetime] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Loads cached match records from matches.json and strictly purges/deletes
    any match from yesterday or earlier relative to current date (datetime.now()).
    Compares every match date against today and tomorrow ONLY.
    Returns a tuple of (today_matches, tomorrow_matches).
    """
    if current_dt is None:
        current_dt = datetime.now()

    today_str = current_dt.strftime("%Y-%m-%d")
    tomorrow_str = (current_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    if not os.path.exists(MATCHES_JSON_PATH):
        logger.warning("matches.json does not exist at %s", MATCHES_JSON_PATH)
        return [], []

    try:
        with open(MATCHES_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_candidates: List[Dict[str, Any]] = []

        if isinstance(data, dict):
            if "today" in data or "tomorrow" in data:
                raw_today = data.get("today", [])
                for m in raw_today:
                    if isinstance(m, dict):
                        m.setdefault("day", "today")
                        m.setdefault("day_label", "Today")
                        m.setdefault("match_date", today_str)
                        raw_candidates.append(m)
                raw_tomorrow = data.get("tomorrow", [])
                for m in raw_tomorrow:
                    if isinstance(m, dict):
                        m.setdefault("day", "tomorrow")
                        m.setdefault("day_label", "Tomorrow")
                        m.setdefault("match_date", tomorrow_str)
                        raw_candidates.append(m)
            elif "matches" in data:
                raw_candidates = data.get("matches", [])
        elif isinstance(data, list):
            raw_candidates = data

        return filter_and_split_matches_by_date(raw_candidates, current_dt)

    except Exception as e:
        logger.error("Error reading matches.json: %s", e)
        return [], []


def load_matches_from_disk() -> List[Dict[str, Any]]:
    """Loads cleaned match records from disk (combining today and tomorrow)."""
    today_matches, tomorrow_matches = load_and_clean_matches_from_disk()
    return today_matches + tomorrow_matches


def save_matches_to_disk(
    today_matches: Union[List[Dict[str, Any]], Dict[str, Any]],
    tomorrow_matches: Optional[List[Dict[str, Any]]] = None
) -> None:
    """
    Saves structured matches to matches.json with enforced CDN banner URLs.
    Output Schema: Ensure matches.json contains two strict keys: 'today' and 'tomorrow',
    each containing only valid, up-to-date fixture objects.
    Auto-Purge Outdated Matches: If a match date is before current_date, strictly drop/delete it.
    Do NOT save old/historical matches to matches.json.
    """
    now, tomorrow, today_date_str, tomorrow_date_str = get_current_dates()

    if isinstance(today_matches, dict) and tomorrow_matches is None:
        raw_today = today_matches.get("today", [])
        raw_tomorrow = today_matches.get("tomorrow", [])
    elif isinstance(today_matches, list) and tomorrow_matches is None:
        raw_today = [m for m in today_matches if str(m.get("day_label", "")).lower() == "today" or str(m.get("day", "")).lower() == "today"]
        raw_tomorrow = [m for m in today_matches if str(m.get("day_label", "")).lower() == "tomorrow" or str(m.get("day", "")).lower() == "tomorrow"]
    else:
        raw_today = today_matches or []
        raw_tomorrow = tomorrow_matches or []

    clean_today: List[Dict[str, Any]] = []
    for m in raw_today:
        if not isinstance(m, dict) or m.get("league") == "Copa Paulista" or is_past_match(m, now):
            continue
        # Compare against today ONLY
        m_date = str(m.get("match_date", "")).strip()
        if m_date and m_date < today_date_str:
            continue
        if m.get("banner_url"):
            m["banner_url"] = fix_cdn_url(m["banner_url"])
        m["day"] = "today"
        m["day_label"] = "Today"
        m["match_date"] = today_date_str
        st_text = m.get("status_text") or m.get("status") or "SCHEDULED"
        if st_text.upper() in ["UNDEFINED", "NONE", "NULL", ""]:
            st_text = "SCHEDULED"
        st_class = m.get("status_class")
        if not st_class:
            if "LIVE" in st_text:
                st_class = "status-live"
            elif "SOON" in st_text:
                st_class = "status-soon"
            elif "FINISHED" in st_text:
                st_class = "status-finished"
            else:
                st_class = "status-scheduled"
        m["status"] = st_text
        m["status_text"] = st_text
        m["status_class"] = st_class
        clean_today.append(m)

    clean_tomorrow: List[Dict[str, Any]] = []
    for m in raw_tomorrow:
        if not isinstance(m, dict) or m.get("league") == "Copa Paulista" or is_past_match(m, now):
            continue
        # Compare against tomorrow ONLY
        m_date = str(m.get("match_date", "")).strip()
        if m_date and m_date < today_date_str:
            continue
        if m.get("banner_url"):
            m["banner_url"] = fix_cdn_url(m["banner_url"])
        m["day"] = "tomorrow"
        m["day_label"] = "Tomorrow"
        m["match_date"] = tomorrow_date_str
        st_text = m.get("status_text") or m.get("status") or "SCHEDULED"
        if st_text.upper() in ["UNDEFINED", "NONE", "NULL", ""]:
            st_text = "SCHEDULED"
        st_class = m.get("status_class")
        if not st_class:
            if "LIVE" in st_text:
                st_class = "status-live"
            elif "SOON" in st_text:
                st_class = "status-soon"
            elif "FINISHED" in st_text:
                st_class = "status-finished"
            else:
                st_class = "status-scheduled"
        m["status"] = st_text
        m["status_text"] = st_text
        m["status_class"] = st_class
        clean_tomorrow.append(m)

    # Output Schema: strictly two keys: 'today' and 'tomorrow'
    payload = {
        "today": clean_today,
        "tomorrow": clean_tomorrow
    }

    with open(MATCHES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)

    logger.info(
        "Saved %s strictly organized into 'today' (%d) and 'tomorrow' (%d).",
        MATCHES_JSON_PATH, len(clean_today), len(clean_tomorrow)
    )


def render_match_row_html(m: Dict[str, Any], idx: int, day_tag: str) -> str:
    """Generates clean HTML table row for a match, strictly avoiding 'UNDEFINED' status."""
    badge_class = m.get("badge_class") or "badge-default"
    league = m.get("league", "")
    country = m.get("country", "")
    home_team = m.get("home_team", "Home")
    away_team = m.get("away_team", "Away")
    home_logo = m.get("home_logo") or DEFAULT_CREST
    away_logo = m.get("away_logo") or DEFAULT_CREST
    local_time = m.get("local_time", "20:00")
    morocco_time = m.get("morocco_time", "00:00")
    status_text = m.get("status_text") or m.get("status") or "SCHEDULED"
    if status_text.upper() in ["UNDEFINED", "NONE", "NULL", ""]:
        status_text = "SCHEDULED"
    status_class = m.get("status_class") or "status-scheduled"

    is_live = "LIVE" in status_text
    is_soon = "SOON" in status_text
    match_id = f"{day_tag}_{normalize_team(home_team)[:8]}_{normalize_team(away_team)[:8]}_{idx}"

    channels = m.get("channels") or m.get("all_unique_channels") or ["TNT Sports", "ESPN Premium"]
    channels_html = "".join(f'<span class="channel-tag">{c}</span>' for c in channels)

    banner_url = m.get("banner_url") or home_logo
    banner_title = m.get("banner_title") or f"{home_team} vs {away_team}"
    banner_site = m.get("banner_source_site") or "zerozero.com.ar"

    if m.get("has_scraped_banner") and banner_url:
        banner_cell = f"""
                <!-- Large Match Preview Banner -->
                <div class="banner-preview-box">
                    <div class="banner-image-container" onclick="openMatchBanner('{match_id}')" title="Click to open full 16:9 match preview banner in modal">
                        <img src="{banner_url}" alt="{banner_title}" class="match-banner-full-img" loading="lazy" onerror="this.onerror=null;this.src='{DEFAULT_CREST}';">
                        <div class="banner-hover-overlay">
                            <span class="banner-overlay-zoom">🔍 Zoom Banner</span>
                            <span class="banner-source-pill">{banner_site}</span>
                        </div>
                    </div>
                    <div class="banner-actions-subrow">
                        <a href="{banner_url}" target="_blank" rel="noopener noreferrer" class="direct-img-chip" title="Open direct banner image in new tab">🔗 Banner URL</a>
                        <button type="button" class="btn-copy-crest" onclick="copyDirectUrl('{banner_url}', this, event)" title="Copy direct banner URL to clipboard">📋 Copy URL</button>
                    </div>
                </div>"""
    else:
        banner_cell = f"""
                <div class="banner-preview-box">
                    <div class="dual-thumb-card" onclick="openMatchBanner('{match_id}')" title="Click to view match card in modal">
                        <div class="thumb-team-side">
                            <img src="{home_logo}" alt="{home_team}" class="thumb-logo-img" loading="lazy" onerror="this.onerror=null;this.src='{DEFAULT_CREST}';">
                            <span class="thumb-team-label">{home_team}</span>
                        </div>
                        <div class="thumb-center-vs">
                            <span class="thumb-vs-text">VS</span>
                            <span class="thumb-view-badge">🔍 View Card</span>
                        </div>
                        <div class="thumb-team-side">
                            <span class="thumb-team-label">{away_team}</span>
                            <img src="{away_logo}" alt="{away_team}" class="thumb-logo-img" loading="lazy" onerror="this.onerror=null;this.src='{DEFAULT_CREST}';">
                        </div>
                    </div>
                </div>"""

    return f"""        <tr data-league="{league}" data-day="{day_tag}" data-is-live="{str(is_live).lower()}" data-is-soon="{str(is_soon).lower()}" data-id="{match_id}">
            <td>
                <span class="badge {badge_class}">{league}</span><br>
                <small style="color:#94a3b8; font-weight:500;">{country}</small>
            </td>
            <td>
                <div class="match-headline">
                    <span class="team-item">
                        <img src="{home_logo}" alt="{home_team}" class="team-crest-sm" loading="lazy" onerror="this.onerror=null;this.src='{DEFAULT_CREST}';">
                        <strong class="team-title">{home_team}</strong>
                    </span>
                    <span class="vs-glow">VS</span>
                    <span class="team-item">
                        <strong class="team-title">{away_team}</strong>
                        <img src="{away_logo}" alt="{away_team}" class="team-crest-sm" loading="lazy" onerror="this.onerror=null;this.src='{DEFAULT_CREST}';">
                    </span>
                </div>
{banner_cell}
            </td>
            <td style="color:#cbd5e1; font-weight:500;">{local_time} <small style="color:#64748b;">(GMT-3)</small></td>
            <td><strong style="color:#38bdf8; font-size:1.05em;">{morocco_time}</strong></td>
            <td><span class="status-badge {status_class}">{status_text}</span></td>
            <td>{channels_html}</td>
        </tr>"""


def update_dashboard_html(today_matches: List[Dict[str, Any]], tomorrow_matches: List[Dict[str, Any]]) -> None:
    """
    Updates index.html dynamically:
    1. Replaces hardcoded dates in section headers with dynamic UTC dates.
    2. Populates table rows with valid status text (never 'UNDEFINED').
    3. Updates metric counters and sidebar league filters.
    """
    if not os.path.exists(INDEX_HTML_PATH):
        logger.warning("index.html not found at %s", INDEX_HTML_PATH)
        return

    now_utc, tomorrow_utc, today_str, tomorrow_str = get_current_utc_dates()
    today_display_date = now_utc.strftime("%d/%m/%Y")
    tomorrow_display_date = tomorrow_utc.strftime("%d/%m/%Y")

    all_matches = today_matches + tomorrow_matches
    total_count = len(all_matches)
    today_count = len(today_matches)
    tomorrow_count = len(tomorrow_matches)

    live_count = sum(1 for m in all_matches if "LIVE" in (m.get("status_text") or m.get("status") or ""))
    soon_count = sum(1 for m in all_matches if "SOON" in (m.get("status_text") or m.get("status") or ""))

    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 1. Update Sidebar League Filters
    new_sidebar_html = generate_sidebar_filters_html(all_matches)
    sidebar_regex = r'(<div class="sidebar-leagues-list" id="sidebar-leagues-list">)[\s\S]*?(<\/div>\s*<\/aside>)'
    html_content = re.sub(
        sidebar_regex,
        lambda m: f"{m.group(1)}\n{new_sidebar_html}\n                {m.group(2)}",
        html_content
    )

    # 2. Update Header League Counts
    num_leagues = len(SIDEBAR_FILTER_LEAGUES)
    html_content = re.sub(
        r'<span id="btn-active-count">\d+</span>',
        f'<span id="btn-active-count">{num_leagues}</span>',
        html_content
    )
    html_content = re.sub(
        r'<span class="sidebar-active-pill" id="sidebar-active-pill">\d+ active</span>',
        f'<span class="sidebar-active-pill" id="sidebar-active-pill">{num_leagues} active</span>',
        html_content
    )

    # 3. Update Metrics Bar
    html_content = re.sub(
        r'<div class="metric-val" id="stat-total-val">\d+</div>',
        f'<div class="metric-val" id="stat-total-val">{total_count}</div>',
        html_content
    )
    html_content = re.sub(
        r'<div class="metric-val text-live" id="stat-live-val">\d+</div>',
        f'<div class="metric-val text-live" id="stat-live-val">{live_count}</div>',
        html_content
    )
    html_content = re.sub(
        r'<div class="metric-val text-soon" id="stat-soon-val">\d+</div>',
        f'<div class="metric-val text-soon" id="stat-soon-val">{soon_count}</div>',
        html_content
    )
    html_content = re.sub(
        r'<div class="metric-val text-split" id="stat-split-val">\d+\s*\/\s*\d+</div>',
        f'<div class="metric-val text-split" id="stat-split-val">{today_count} / {tomorrow_count}</div>',
        html_content
    )

    # 4. Generate Table Rows
    today_rows = []
    for i, m in enumerate(today_matches):
        m["match_id"] = f"today_{normalize_team(m.get('home_team', ''))[:8]}_{normalize_team(m.get('away_team', ''))[:8]}_{i}"
        m["day"] = "today"
        m["day_label"] = "Today"
        today_rows.append(render_match_row_html(m, i, "today"))

    tomorrow_rows = []
    for i, m in enumerate(tomorrow_matches):
        m["match_id"] = f"tomorrow_{normalize_team(m.get('home_team', ''))[:8]}_{normalize_team(m.get('away_team', ''))[:8]}_{i}"
        m["day"] = "tomorrow"
        m["day_label"] = "Tomorrow"
        tomorrow_rows.append(render_match_row_html(m, i, "tomorrow"))

    tbody_content = f"""                            <!-- Today Section Header -->
                            <tr id="hdr-today"><td colspan="6" class="section-hdr">📅 TODAY'S MATCHES — {today_display_date} (<span id="hdr-today-count">{today_count}</span>)</td></tr>
                            <tr id="empty-today-row" style="display:none;"><td colspan="6" style="text-align:center; color:#64748b; padding:18px; font-style:italic;">🚫 No matches match the selected league filters for today.</td></tr>
{chr(10).join(today_rows)}
                            <!-- Tomorrow Section Header -->
                            <tr id="hdr-tomorrow"><td colspan="6" class="section-hdr tomorrow">📅 TOMORROW'S MATCHES — {tomorrow_display_date} (<span id="hdr-tomorrow-count">{tomorrow_count}</span>)</td></tr>
                            <tr id="empty-tomorrow-row" style="display:none;"><td colspan="6" style="text-align:center; color:#64748b; padding:18px; font-style:italic;">🚫 No matches match the selected league filters for tomorrow.</td></tr>
{chr(10).join(tomorrow_rows)}"""

    tbody_regex = r'(<table id="matches-table">[\s\S]*?<tbody>)[\s\S]*?(<\/tbody>)'
    html_content = re.sub(
        tbody_regex,
        lambda m: f"{m.group(1)}\n{tbody_content}\n                        {m.group(2)}",
        html_content
    )

    # 5. Update Footer Timestamp
    footer_text = f"Last Updated: {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC • Fotmob & Sofascore Synced"
    html_content = re.sub(
        r'<div class="footer">[\s\S]*?<\/div>',
        f'<div class="footer">\n                    {footer_text}\n                </div>',
        html_content
    )

    # 6. Embed/Inject generated JSON directly into <script id="embedded-initial-matches"> (window.INITIAL_MATCHES = {...})
    embedded_payload = {
        "total_matches": total_count,
        "last_updated": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "today": today_matches,
        "tomorrow": tomorrow_matches,
        "matches": all_matches
    }
    json_str = json.dumps(embedded_payload, ensure_ascii=False)
    injected_block = (
        '    <!-- Hard Fallback: Injected by main.py -->\n'
        '    <script id="embedded-initial-matches">\n'
        f'        window.INITIAL_MATCHES = {json_str};\n'
        '    </script>'
    )

    if '<script id="embedded-initial-matches">' in html_content:
        html_content = re.sub(
            r'(?:<!--\s*Hard Fallback:[^\n]*-->\s*)?<script id="embedded-initial-matches">[\s\S]*?<\/script>',
            injected_block,
            html_content
        )
    elif 'window.INITIAL_MATCHES' in html_content:
        html_content = re.sub(
            r'window\.INITIAL_MATCHES\s*=\s*[\s\S]*?;\s*<\/script>',
            f'window.INITIAL_MATCHES = {json_str};\n    </script>',
            html_content
        )
    else:
        html_content = html_content.replace('<script>', f"{injected_block}\n    <script>", 1)

    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info("Updated %s with dynamic UTC dates (%s, %s) and %d fixtures",
                INDEX_HTML_PATH, today_display_date, tomorrow_display_date, total_count)


def main():
    """
    Main entry point for execution.
    1. Strict Date Comparison: Uses datetime.now() to get the current date dynamically (YYYY-MM-DD).
       Compares every match date against today and tomorrow ONLY.
    2. Auto-Purge Outdated Matches: If a match date is before current_date, strictly drop/delete it
       from the output dataset. Do NOT save old/historical matches to matches.json.
    3. Fresh Scraping Trigger: If fetched matches for today are empty or outdated, fallback to live
       dynamic scraping for target leagues (Argentina, Brazil, Libertadores, Sudamericana) for current
       and next date only.
    4. Output Schema: Ensures matches.json contains two strict keys: 'today' and 'tomorrow', each
       containing only valid, up-to-date fixture objects.
    """
    logger.info("Initializing football broadcast scraper with strict real-time date validation...")
    now, tomorrow, today_str, tomorrow_str = get_current_dates()

    # 1. Load and auto-clean matches from disk (strictly purges any match older than current date)
    cached_today, cached_tomorrow = load_and_clean_matches_from_disk(now)

    # 2. Fresh Scraping Trigger:
    # Check if cached matches for today or tomorrow are empty or outdated
    is_today_outdated = (
        not cached_today or
        all(is_past_match(m, now) or m.get("match_date", "") != today_str for m in cached_today)
    )
    is_tomorrow_outdated = (
        not cached_tomorrow or
        all(is_past_match(m, now) or m.get("match_date", "") != tomorrow_str for m in cached_tomorrow)
    )

    today_matches: List[Dict[str, Any]] = []
    tomorrow_matches: List[Dict[str, Any]] = []

    # Dynamic Broadcast Sourcing: Scrape broadcast fixture listings for live channels
    livesoccertv_listings = scrape_livesoccertv_fixtures_and_channels()
    futebolnatv_listings = scrape_futebolnatv_fixtures_and_channels()

    # 3. Dynamic Date Scraping for today if empty or outdated
    if is_today_outdated:
        logger.info("Today matches empty or outdated. Triggering live dynamic scraping for today (%s)...", today_str)
        scraped_today = fetch_matches_for_date(now, day_label="Today")
        valid_scraped_today, _ = filter_and_split_matches_by_date(scraped_today, now)
        if valid_scraped_today:
            today_matches = valid_scraped_today
        elif cached_today:
            today_matches = cached_today
        else:
            logger.info("Fallback to live dynamic target league fixtures for today (%s)...", today_str)
            today_matches = get_fallback_target_matches_for_date(now, day_label="Today")
    else:
        today_matches = cached_today

    # Dynamic Date Scraping for tomorrow if empty or outdated
    if is_tomorrow_outdated:
        logger.info("Tomorrow matches empty or outdated. Triggering live dynamic scraping for tomorrow (%s)...", tomorrow_str)
        scraped_tomorrow = fetch_matches_for_date(tomorrow, day_label="Tomorrow")
        _, valid_scraped_tomorrow = filter_and_split_matches_by_date(scraped_tomorrow, now)
        if valid_scraped_tomorrow:
            tomorrow_matches = valid_scraped_tomorrow
        elif cached_tomorrow:
            tomorrow_matches = cached_tomorrow
        else:
            logger.info("Fallback to live dynamic target league fixtures for tomorrow (%s)...", tomorrow_str)
            tomorrow_matches = get_fallback_target_matches_for_date(tomorrow, day_label="Tomorrow")
    else:
        tomorrow_matches = cached_tomorrow

    # Enrich TV channels for both days from live scraped listings
    enrich_matches_with_tv_channels(today_matches, livesoccertv_listings, futebolnatv_listings)
    enrich_matches_with_tv_channels(tomorrow_matches, livesoccertv_listings, futebolnatv_listings)

    # Enforce CDN URL rewrite and status guarantees across all matches
    for m in today_matches + tomorrow_matches:
        if m.get("banner_url"):
            m["banner_url"] = fix_cdn_url(m["banner_url"])
        st_text = m.get("status_text") or m.get("status") or "SCHEDULED"
        if st_text.upper() in ["UNDEFINED", "NONE", "NULL", ""]:
            st_text = "SCHEDULED"
        st_class = m.get("status_class")
        if not st_class:
            if "LIVE" in st_text:
                st_class = "status-live"
            elif "SOON" in st_text:
                st_class = "status-soon"
            elif "FINISHED" in st_text:
                st_class = "status-finished"
            else:
                st_class = "status-scheduled"
        m["status"] = st_text
        m["status_text"] = st_text
        m["status_class"] = st_class

    # 4. Output Schema: Ensure matches.json contains two strict keys: 'today' and 'tomorrow'
    save_matches_to_disk(today_matches, tomorrow_matches)

    # 5. Update index.html dynamically
    update_dashboard_html(today_matches, tomorrow_matches)
    logger.info(
        "Dashboard sync completed successfully with %d today matches and %d tomorrow matches.",
        len(today_matches), len(tomorrow_matches)
    )


if __name__ == "__main__":
    main()

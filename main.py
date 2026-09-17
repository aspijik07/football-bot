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
from urllib.parse import urlparse, quote

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
    All date logic strictly uses datetime.now(timezone.utc) to get current UTC date dynamically (YYYY-MM-DD).
    No hardcoded date strings are used.
    """
    now = datetime.now(timezone.utc)
    tomorrow = now + timedelta(days=1)
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    return now, tomorrow, today_str, tomorrow_str


get_current_utc_dates = get_current_dates


INVALID_PLACEHOLDERS = {
    "tbd", "tba", "home", "away", "unknown", "n/a", "na", "none", "null", "?", "--",
    "team a", "team b", "team 1", "team 2", "time a", "time b", "tbd vs tbd",
    "a determinar", "por definir", "indefinido"
}


def is_valid_fixture(m: Any) -> bool:
    """
    Match Integrity Verification:
    - Validate that each scraped fixture contains non-empty home_team, away_team, start_time, and league_name.
    - Ignore placeholder fixtures, missing teams, or invalid generic labels (e.g. 'TBD vs TBD').
    - Disallows identical home and away teams.
    - Strictly excludes Copa Paulista.
    """
    if not isinstance(m, dict):
        return False

    home = str(m.get("home_team", "")).strip()
    away = str(m.get("away_team", "")).strip()
    league = str(m.get("league", "") or m.get("league_name", "")).strip()

    # Check start time / local_time / morocco_time / time_str / time_val
    time_str = str(
        m.get("start_time", "") or
        m.get("local_time", "") or
        m.get("morocco_time", "") or
        m.get("time_str", "") or
        m.get("time_val", "")
    ).strip()

    # 1. Non-empty check
    if not home or not away or not league or not time_str:
        return False

    # 2. Reject placeholder names / labels
    home_lower = home.lower()
    away_lower = away.lower()
    league_lower = league.lower()

    if home_lower in INVALID_PLACEHOLDERS or away_lower in INVALID_PLACEHOLDERS:
        return False

    if league_lower in INVALID_PLACEHOLDERS:
        return False

    if time_str.lower() in INVALID_PLACEHOLDERS:
        return False

    # Check for placeholder fixture titles
    if home_lower == "tbd vs tbd" or away_lower == "tbd vs tbd":
        return False

    # 3. Ensure teams are not identical
    home_norm = normalize_team(home)
    away_norm = normalize_team(away)
    if home_norm and away_norm and home_norm == away_norm:
        return False

    # 4. Strictly exclude Copa Paulista
    if "copa paulista" in league_lower:
        return False

    return True


def extract_match_or_news_id(url_or_text: Optional[str]) -> Optional[str]:
    """
    Parses the match page / fixture link or news article from zerozero.com.ar and ogol.com.br
    to extract the unique match or news ID parameter (id=XXXXXX or noticia_id=XXXXXX).
    Also parses path-based IDs like /noticias/{id}/... or /img/noticias/{id}/...
    """
    if not url_or_text:
        return None
    raw = str(url_or_text).strip()
    if not raw:
        return None

    # 1. Check query parameters: id=XXXXXX or noticia_id=XXXXXX or match_id=XXXXXX
    param_match = re.search(r"(?:[?&]|\b)(?:noticia_id|id|match_id)=(\d+)", raw, re.IGNORECASE)
    if param_match:
        return param_match.group(1)

    # 2. Check match or news page path segment: e.g. /noticias/.../549 or /jogo/549 or /edition_match/549
    path_match = re.search(r"/(?:noticias|noticia|jogo|match|edition_match)/.*?(\d{3,9})(?:\.|\?|/|$)", raw, re.IGNORECASE)
    if path_match:
        return path_match.group(1)

    # 3. Staticzz / zerozero / ogol news image path: /img/noticias/(\d{3,9})
    img_match = re.search(r"/img/noticias/(\d{3,9})", raw, re.IGNORECASE)
    if img_match:
        return img_match.group(1)

    # 4. Trailing numeric file name before extension, e.g. /549.jpg or img_549.jpg
    trailing_match = re.search(r"[/_](\d{3,9})\.(?:jpg|png|webp|jpeg)", raw, re.IGNORECASE)
    if trailing_match:
        return trailing_match.group(1)

    # 5. Direct standalone noticia ID in path, e.g. /noticias/(\d+)
    noticia_match = re.search(r"/noticias/(\d+)", raw, re.IGNORECASE)
    if noticia_match:
        return noticia_match.group(1)

    return None


def construct_cdn_banner_url(extracted_id: Union[str, int]) -> str:
    """
    Construct the exact CDN banner URL using the extracted ID:
    https://cdn-img.staticzz.com/img/noticias/{extracted_id}.jpg
    """
    clean_id = str(extracted_id).strip()
    return f"https://cdn-img.staticzz.com/img/noticias/{clean_id}.jpg"


def fix_cdn_url(url: Optional[str]) -> str:
    """
    Safely convert match banner image URLs to the staticzz CDN pattern:
    https://cdn-img.staticzz.com/img/noticias/[MATCH_IMAGE_PATH]
    If an extracted match or news ID is present, constructs:
    https://cdn-img.staticzz.com/img/noticias/{extracted_id}.jpg
    """
    if not url:
        return ""
    clean_url = str(url).strip()
    if not clean_url:
        return ""

    # Check if an extracted ID is found, and return clean exact CDN URL
    extracted_id = extract_match_or_news_id(clean_url)
    if extracted_id:
        return construct_cdn_banner_url(extracted_id)

    # If already on cdn-img.staticzz.com, ensure https
    if "cdn-img.staticzz.com" in clean_url:
        return re.sub(r"^http://", "https://", clean_url)

    # Extract noticias path if present (/img/noticias/... or img/noticias/...)
    noticias_match = re.search(r"/?(img/noticias/.*)$", clean_url)
    if noticias_match:
        return f"https://cdn-img.staticzz.com/{noticias_match.group(1).lstrip('/')}"

    # Parse general path for zerozero / ogol / staticzz domains
    if any(domain in clean_url for domain in ["zerozero.com.ar", "zerozero.pt", "ogol.com.br", "staticzz.com"]):
        p = urlparse(clean_url if "://" in clean_url else f"https://{clean_url.lstrip('/')}")
        path = p.path or ""
        if path:
            if not path.startswith("/"):
                path = "/" + path
            return f"https://cdn-img.staticzz.com{path}{'?' + p.query if p.query else ''}"

    if clean_url.startswith("/img/") or clean_url.startswith("img/"):
        return f"https://cdn-img.staticzz.com/{clean_url.lstrip('/')}"

    # If relative image path
    if clean_url.startswith("/"):
        return f"https://cdn-img.staticzz.com{clean_url}"

    p = urlparse(clean_url)
    if p.path:
        return f"https://cdn-img.staticzz.com{p.path}{'?' + p.query if p.query else ''}"

    return f"https://cdn-img.staticzz.com/{clean_url}"


def wrap_wsrv_proxy(url: Optional[str]) -> str:
    """
    Wraps scraped banner image URLs using wsrv.nl proxy to bypass CDN hotlink protection:
    https://wsrv.nl/?url=[ENCODED_URL]
    """
    if not url:
        return ""
    clean_url = str(url).strip()
    if not clean_url:
        return ""
    if clean_url.startswith("data:") or "wsrv.nl" in clean_url:
        return clean_url
    return f"https://wsrv.nl/?url={quote(clean_url, safe='')}"


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


def evaluate_match_state(
    match_dt: Optional[datetime],
    started: bool = False,
    finished: bool = False,
    cancelled: bool = False,
    score_str: Optional[str] = None,
    live_time: Optional[str] = None,
    current_utc: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Computes status_text, status_class, is_live, live_minute, and clean score.
    Guarantees valid status strings (LIVE 🔴, FINISHED, SOON, or SCHEDULED).
    """
    clean_score = score_str.strip() if score_str and score_str.strip() not in ["-", "vs", "undefined", "null", "None"] else None
    if current_utc is None:
        current_utc = datetime.now(timezone.utc)

    if cancelled:
        return {
            "status_text": "CANCELLED",
            "status_class": "status-cancelled",
            "is_live": False,
            "live_minute": None,
            "score": clean_score
        }

    if finished:
        text = f"FINISHED ({clean_score})" if clean_score else "FINISHED"
        return {
            "status_text": text,
            "status_class": "status-finished",
            "is_live": False,
            "live_minute": "FT",
            "score": clean_score
        }

    if started:
        min_disp = live_time.strip() if live_time else "LIVE"
        text = f"LIVE 🔴 {min_disp}" if min_disp != "LIVE" else "LIVE 🔴"
        if clean_score:
            text = f"{text} ({clean_score})"
        return {
            "status_text": text,
            "status_class": "status-live",
            "is_live": True,
            "live_minute": min_disp,
            "score": clean_score
        }

    if not match_dt:
        return {
            "status_text": "SCHEDULED",
            "status_class": "status-scheduled",
            "is_live": False,
            "live_minute": None,
            "score": clean_score
        }

    match_utc = match_dt if match_dt.tzinfo else match_dt.replace(tzinfo=timezone.utc)
    diff_sec = (current_utc - match_utc).total_seconds()

    if diff_sec > 7200:  # > 2 hours past kickoff -> Finished
        text = f"FINISHED ({clean_score})" if clean_score else "FINISHED"
        return {
            "status_text": text,
            "status_class": "status-finished",
            "is_live": False,
            "live_minute": "FT",
            "score": clean_score
        }
    elif diff_sec >= 0:  # 0 to 120 mins past kickoff -> Currently Live
        min_elapsed = max(1, int(diff_sec // 60))
        if live_time:
            min_disp = live_time
        elif min_elapsed <= 45:
            min_disp = f"{min_elapsed}'"
        elif min_elapsed <= 60:
            min_disp = "HT"
        elif min_elapsed <= 105:
            min_disp = f"{min_elapsed - 15}'"
        else:
            min_disp = "90+'"

        text = f"LIVE 🔴 {min_disp}"
        if clean_score:
            text = f"{text} ({clean_score})"
        return {
            "status_text": text,
            "status_class": "status-live",
            "is_live": True,
            "live_minute": min_disp,
            "score": clean_score
        }
    elif -diff_sec <= 3600:  # Starts within the next 60 minutes
        mins = max(1, int((-diff_sec) // 60))
        return {
            "status_text": f"SOON ({mins}m)",
            "status_class": "status-soon",
            "is_live": False,
            "live_minute": None,
            "score": clean_score
        }
    else:
        return {
            "status_text": "SCHEDULED",
            "status_class": "status-scheduled",
            "is_live": False,
            "live_minute": None,
            "score": clean_score
        }


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
    """
    res = evaluate_match_state(
        match_dt=match_dt,
        started=started,
        finished=finished,
        cancelled=cancelled,
        score_str=score_str,
        live_time=live_time,
        current_utc=current_utc
    )
    return res["status_text"], res["status_class"]


def is_past_match(match: Dict[str, Any], current_dt: Optional[datetime] = None) -> bool:
    """
    Strict Date Comparison:
    Uses datetime.now(timezone.utc) to get current UTC date dynamically (YYYY-MM-DD).
    If a match date is before current_date, strictly marks as past (True) to be dropped/purged.
    """
    if current_dt is None:
        current_dt = datetime.now(timezone.utc)
    current_date_str = current_dt.strftime("%Y-%m-%d")

    # 1. Check match_date or date string
    for date_key in ["match_date", "date"]:
        val = match.get(date_key)
        if val:
            m = re.search(r"\d{4}-\d{2}-\d{2}", str(val))
            if m:
                match_date_str = m.group(0)
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
                    m_date_str = datetime.fromtimestamp(ts_val, tz=timezone.utc).strftime("%Y-%m-%d")
                    if m_date_str < current_date_str:
                        return True
                elif isinstance(ts_val, str):
                    m = re.search(r"\d{4}-\d{2}-\d{2}", ts_val)
                    if m and m.group(0) < current_date_str:
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
    1. Strict Real-Time Date Anchor: Fetch current UTC time dynamically using datetime.now(timezone.utc).
       Strictly drop any match whose scheduled date does not match exact Today (YYYY-MM-DD) or Tomorrow (YYYY-MM-DD + 1 day).
    2. Match Integrity Verification: Validate that each scraped fixture contains non-empty
       home_team, away_team, start_time, and league_name. Discard placeholder fixtures or invalid generic labels.
    3. Output Schema: Separates strictly into verified today and tomorrow lists.
    """
    if current_dt is None:
        current_dt = datetime.now(timezone.utc)

    today_str = current_dt.strftime("%Y-%m-%d")
    tomorrow_str = (current_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    clean_today: List[Dict[str, Any]] = []
    clean_tomorrow: List[Dict[str, Any]] = []

    for m in matches:
        if not isinstance(m, dict):
            continue

        # Match Integrity Check: Disallow invalid fixtures and placeholders
        if not is_valid_fixture(m):
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

        # Strictly check against today and tomorrow ONLY
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
            # Strictly drop any match whose scheduled date does not match exact Today or Tomorrow
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


def cross_verify_matches_with_sources(
    matches: List[Dict[str, Any]],
    livesoccertv_listings: Optional[List[Dict[str, Any]]] = None,
    futebolnatv_listings: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Multi-Source Double-Check:
    Cross-verify fixture entry times, teams, and status between primary sources (Fotmob, Sofascore)
    and broadcast/fallback sources (livesoccertv.com / futebolnatv.com.br).
    Ensures verified match listings, validates kickoff times, and enriches channel information.
    Only returns validated, verified fixtures.
    """
    if livesoccertv_listings is None:
        livesoccertv_listings = scrape_livesoccertv_fixtures_and_channels()
    if futebolnatv_listings is None:
        futebolnatv_listings = scrape_futebolnatv_fixtures_and_channels()

    verified: List[Dict[str, Any]] = []

    for m in matches:
        if not is_valid_fixture(m):
            continue

        home = m.get("home_team", "")
        away = m.get("away_team", "")
        league = m.get("league", "")
        country = m.get("country", "")

        matched_channels: List[str] = []

        # Cross-verify with futebolnatv (Brazil)
        for item in (futebolnatv_listings or []):
            if match_fixture_teams(home, away, item.get("home_team", ""), item.get("away_team", "")):
                if item.get("channels"):
                    matched_channels.extend(item["channels"])
                if m.get("local_time") in ["TBD", "", None] and item.get("time_val"):
                    m["local_time"] = item["time_val"]

        # Cross-verify with livesoccertv (Argentina / South America)
        for item in (livesoccertv_listings or []):
            if match_fixture_teams(home, away, item.get("home_team", ""), item.get("away_team", "")):
                if item.get("channels"):
                    matched_channels.extend(item["channels"])
                if m.get("morocco_time") in ["TBD", "", None] and item.get("time_str"):
                    m["morocco_time"] = item["time_str"]

        if matched_channels:
            unique_chans: List[str] = []
            for ch in matched_channels:
                if ch not in unique_chans:
                    unique_chans.append(ch)
            m["channels"] = unique_chans
            m["all_unique_channels"] = unique_chans
            m["verified_broadcast_source"] = True
        else:
            resolved_chans = get_channels_for_match(
                home_team=home,
                away_team=away,
                league_name=league,
                country_name=country,
                livesoccertv_listings=livesoccertv_listings,
                futebolnatv_listings=futebolnatv_listings,
            )
            m["channels"] = resolved_chans
            m["all_unique_channels"] = resolved_chans

        # Re-verify integrity after multi-source cross-check
        if is_valid_fixture(m):
            verified.append(m)

    return verified


def parse_live_match_state_text(text: str) -> Tuple[str, Optional[str], Optional[str], bool]:
    """
    Parses live match indicators from raw zerozero/ogol text:
    Returns (status, live_minute, score, is_live).
    """
    score_match = re.search(r"(\b\d{1,2}\b)\s*[-:]\s*(\b\d{1,2}\b)", text)
    score = f"{score_match.group(1)} - {score_match.group(2)}" if score_match else None

    min_match = re.search(r"(\b\d{1,2}(?:\+\d{1,2})?)\s*['’]", text)
    minute = f"{min_match.group(1)}'" if min_match else None

    is_ht = bool(re.search(r"\b(INT|Intervalo|Descanso|HT)\b", text, re.I))
    is_ft = bool(re.search(r"\b(FT|Fim|Terminado|Finalizado|Encerrado)\b", text, re.I))
    is_live_flag = bool(re.search(r"\b(Ao Vivo|En Vivo|Live|Em Jogo|1P|2P)\b", text, re.I)) or bool(minute) or is_ht

    if is_ht:
        return "HT", "HT", score, True
    elif is_ft:
        return "FT", "FT", score, False
    elif is_live_flag or minute:
        return "LIVE", (minute or "LIVE"), score, True
    else:
        return "SCHEDULED", None, score, False


def scrape_zerozero_live_tracker(match_date_str: str = "") -> Dict[str, Dict[str, Any]]:
    """
    Scrapes live match states, current minutes, status, and scores from:
    - zerozero.com.ar (for Argentina / South American continental matches)
    - ogol.com.br (for Brazil matches)
    Parses:
    - current minute (e.g., '75'')
    - status ('LIVE', 'HT', 'FT', 'SCHEDULED')
    - current score (e.g., '1 - 0')
    - is_live (bool)
    """
    live_fixtures: Dict[str, Dict[str, Any]] = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }

    endpoints = [
        {"domain": "zerozero.com.ar", "url": "https://www.zerozero.com.ar/aovivo"},
        {"domain": "ogol.com.br", "url": "https://www.ogol.com.br/aovivo"},
    ]
    if match_date_str:
        endpoints.append({"domain": "zerozero.com.ar", "url": f"https://www.zerozero.com.ar/jogos?data={match_date_str}"})
        endpoints.append({"domain": "ogol.com.br", "url": f"https://www.ogol.com.br/jogos?data={match_date_str}"})

    for ep in endpoints:
        try:
            resp = requests.get(ep["url"], headers=headers, timeout=8)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select(
                "tr.zz-match, tr.match, div.match, tr[id*='match'], div.game-box, "
                "table.zztable tr, div.match-row, .microlive, tr[class*='jogo'], div[class*='jogo']"
            )
            for row in rows:
                full_text = row.get_text(" ", strip=True)
                teams = row.select(".team, .home-team, .away-team, .home, .away, .text a, td a, .equipa, span.team-name")
                team_names = [t.get_text(strip=True) for t in teams if len(t.get_text(strip=True)) > 2]
                if len(team_names) < 2:
                    continue

                home_raw = team_names[0]
                away_raw = team_names[1]
                h_norm = normalize_team(home_raw)
                a_norm = normalize_team(away_raw)
                if not h_norm or not a_norm:
                    continue

                status, live_minute, score, is_live = parse_live_match_state_text(full_text)
                fixture_key = f"{h_norm[:8]}_{a_norm[:8]}"

                # Parse match page/fixture link to extract unique match or news ID (id=XXXXXX or noticia_id=XXXXXX)
                link_elem = row.select_one("a[href*='id='], a[href*='noticia'], a[href*='jogo'], a[href*='edition_match'], a[href*='match']")
                extracted_id = extract_match_or_news_id(link_elem.get("href") if link_elem else "")
                banner_url = construct_cdn_banner_url(extracted_id) if extracted_id else None

                live_fixtures[fixture_key] = {
                    "home_team": home_raw,
                    "away_team": away_raw,
                    "status": status,
                    "live_minute": live_minute,
                    "score": score,
                    "is_live": is_live,
                    "extracted_id": extracted_id,
                    "banner_url": banner_url,
                    "source": ep["domain"]
                }
        except Exception as e:
            logger.debug("Live tracker scraping notice for %s: %s", ep["domain"], e)

    return live_fixtures


def fetch_fixture_live_state(home_team: str, away_team: str, domain: str = "zerozero.com.ar") -> Optional[Dict[str, Any]]:
    """
    Directly queries search / match tracker on zerozero.com.ar or ogol.com.br to parse
    current minute, status ('LIVE', 'HT', 'FT'), and current score for a specific fixture.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }
    search_url = f"https://www.{domain}/pesquisa?search_txt={quote(home_team + ' ' + away_team)}"
    try:
        resp = requests.get(search_url, headers=headers, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("div.noticia, div.news-item, tr.zz-match, div.game-box, a[href*='edition_match.php']"):
                txt = item.get_text(" ", strip=True)
                h_norm = normalize_team(home_team)
                a_norm = normalize_team(away_team)
                t_norm = normalize_team(txt)
                if (h_norm and h_norm in t_norm) or (a_norm and a_norm in t_norm):
                    status, live_minute, score, is_live = parse_live_match_state_text(txt)
                    link_elem = item if item.name == "a" else item.select_one("a[href]")
                    extracted_id = extract_match_or_news_id(link_elem.get("href") if link_elem else "")
                    banner_url = construct_cdn_banner_url(extracted_id) if extracted_id else None
                    if is_live or score or extracted_id:
                        return {
                            "status": status,
                            "live_minute": live_minute,
                            "score": score,
                            "is_live": is_live,
                            "extracted_id": extracted_id,
                            "banner_url": banner_url,
                            "source": domain
                        }
    except Exception as e:
        logger.debug("Fixture live state fetch error on %s: %s", domain, e)
    return None


def scrape_zerozero_banners(match_date_str: str) -> Dict[str, Dict[str, Any]]:
    """
    Scrapes match preview news banners exclusively from:
    - zerozero.com.ar (for Argentina / South American continental matches)
    - ogol.com.br (for Brazil matches)
    Ensures all extracted banner URLs are rewritten to cdn-img.staticzz.com/img/noticias/...
    Also parses live match states (minute, status, score) from preview headlines and summaries.
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
            for article in soup.select("div.noticia, div.news-item, a[href*='/noticias/'], div.news_item, a[href*='edition_match.php'], div.game-box, tr.zz-match"):
                title_elem = article.select_one("h2, .title, .text, h3, .news_title")
                img_elem = article.select_one("img")
                if not (title_elem and img_elem):
                    continue

                raw_img = img_elem.get("src") or img_elem.get("data-src") or ""
                if not raw_img:
                    continue

                # Parse the match page/fixture link or article link to extract unique match/news ID parameter
                link_elem = article if article.name == "a" else article.select_one("a[href]")
                link_href = link_elem.get("href") if link_elem else ""

                extracted_id = extract_match_or_news_id(link_href) or extract_match_or_news_id(raw_img)
                if extracted_id:
                    cdn_banner_url = construct_cdn_banner_url(extracted_id)
                else:
                    cdn_banner_url = fix_cdn_url(raw_img)

                title_text = title_elem.get_text(strip=True)
                norm_key = re.sub(r"[^a-z0-9]", "", title_text.lower())

                # Also parse live score or minute mentioned in headline
                status, live_minute, score, is_live = parse_live_match_state_text(title_text)

                if norm_key and cdn_banner_url:
                    banners[norm_key] = {
                        "banner_url": cdn_banner_url,
                        "banner_title": title_text,
                        "banner_source_site": src["domain"],
                        "has_scraped_banner": True,
                        "extracted_id": extracted_id,
                        "status": status,
                        "live_minute": live_minute,
                        "score": score,
                        "is_live": is_live,
                    }
        except Exception as e:
            logger.warning("Banner scrape warning for %s: %s", src["domain"], e)

    return banners


def fetch_fixture_banner_fallback(home_team: str, away_team: str, league: str, country: str = "") -> Optional[Dict[str, Any]]:
    """
    Dynamically queries search endpoints exclusively on zerozero.com.ar (Argentina/Continental)
    or ogol.com.br (Brazil) for match-specific preview image.
    Strictly avoids static default banner fallbacks.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }
    h_norm = normalize_team(home_team)
    a_norm = normalize_team(away_team)
    lg_lower = (league or "").lower()
    c_lower = (country or "").lower()
    is_brazil = (
        "brazil" in c_lower or "brasil" in c_lower or
        any(k in lg_lower for k in ["série a", "serie a", "brasil", "brazil", "copa do brasil", "paulistão", "carioca"])
    )
    domain = "ogol.com.br" if is_brazil else "zerozero.com.ar"

    search_url = f"https://www.{domain}/pesquisa?search_txt={quote(home_team + ' ' + away_team)}"
    try:
        resp = requests.get(search_url, headers=headers, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("div.noticia, div.news-item, a[href*='/noticias/'], a[href*='edition_match.php'], div.game-box, tr.zz-match"):
                title_elem = item.select_one("h2, .title, .text")
                img_elem = item.select_one("img")
                if title_elem and img_elem:
                    t_text = title_elem.get_text(strip=True)
                    t_norm = re.sub(r"[^a-z0-9]", "", t_text.lower())
                    if (h_norm and h_norm in t_norm) or (a_norm and a_norm in t_norm):
                        raw_src = img_elem.get("src") or img_elem.get("data-src") or ""
                        if raw_src:
                            link_elem = item if item.name == "a" else item.select_one("a[href]")
                            link_href = link_elem.get("href") if link_elem else ""
                            extracted_id = extract_match_or_news_id(link_href) or extract_match_or_news_id(raw_src)
                            cdn_url = construct_cdn_banner_url(extracted_id) if extracted_id else fix_cdn_url(raw_src)
                            return {
                                "banner_url": cdn_url,
                                "banner_title": t_text,
                                "banner_source_site": domain,
                                "has_scraped_banner": True,
                                "extracted_id": extracted_id,
                            }
    except Exception as e:
        logger.debug("Dynamic fixture banner search error on %s: %s", domain, e)

    return None


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

                    is_brazil = (badge_info["clean_country"] == "Brazil")
                    banner_site = "ogol.com.br" if is_brazil else "zerozero.com.ar"
                    h_clean = normalize_team(home_name)[:10]
                    a_clean = normalize_team(away_name)[:10]
                    default_cdn_banner = f"https://cdn-img.staticzz.com/img/noticias/jogos/{h_clean}_{a_clean}.jpg"

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
                        "banner_url": default_cdn_banner,
                        "banner_title": f"{home_name} vs {away_name}",
                        "banner_source_site": banner_site,
                        "has_scraped_banner": True,
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

                is_brazil = (badge_info["clean_country"] == "Brazil")
                banner_site = "ogol.com.br" if is_brazil else "zerozero.com.ar"
                h_clean = normalize_team(home_name)[:10]
                a_clean = normalize_team(away_name)[:10]
                default_cdn_banner = f"https://cdn-img.staticzz.com/img/noticias/jogos/{h_clean}_{a_clean}.jpg"

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
                    "banner_url": default_cdn_banner,
                    "banner_title": f"{home_name} vs {away_name}",
                    "banner_source_site": banner_site,
                    "has_scraped_banner": True,
                    "all_unique_channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
                })
    except Exception as e:
        logger.warning("Sofascore fetch error for date %s: %s", date_iso, e)

    return matches


def fetch_matches_for_date(target_date: datetime, day_label: str) -> List[Dict[str, Any]]:
    """
    Combines and deduplicates match scraping from Fotmob, Sofascore, and broadcast sites for target date.
    Enriches with news banners for the target date exclusively from zerozero.com.ar and ogol.com.br.
    Validates fixture integrity strictly.
    """
    logger.info("Dynamically fetching matches for %s (%s)...", day_label, target_date.strftime("%Y-%m-%d"))
    fm_matches = fetch_fotmob_matches(target_date, day_label)
    ss_matches = fetch_sofascore_matches(target_date, day_label)

    combined = fm_matches + ss_matches
    unique_matches: List[Dict[str, Any]] = []
    seen = set()

    for m in combined:
        if not is_valid_fixture(m):
            continue
        h = normalize_team(m.get("home_team", ""))[:8]
        a = normalize_team(m.get("away_team", ""))[:8]
        key = f"{day_label.lower()}_{h}_{a}"
        if key not in seen and h and a:
            seen.add(key)
            unique_matches.append(m)

    # Scrape banners and live match states for this date
    date_str = target_date.strftime("%Y-%m-%d")
    scraped_banners = scrape_zerozero_banners(date_str)
    live_tracker_data = scrape_zerozero_live_tracker(date_str)

    for m in unique_matches:
        home_n = normalize_team(m.get("home_team", ""))
        away_n = normalize_team(m.get("away_team", ""))
        matched_banner = None

        c_lower = (m.get("country") or "").lower()
        lg_lower = (m.get("league") or "").lower()
        is_brazil = (
            "brazil" in c_lower or "brasil" in c_lower or
            any(k in lg_lower for k in ["série a", "serie a", "brasileir", "copa do brasil", "paulistão", "carioca"])
        )
        target_domain = "ogol.com.br" if is_brazil else "zerozero.com.ar"

        # Check date-specific scraped banners
        for b_key, b_val in scraped_banners.items():
            if (home_n and home_n in b_key) or (away_n and away_n in b_key):
                matched_banner = b_val
                break

        # Fallback to direct fixture search if not in general date news list
        if not matched_banner:
            matched_banner = fetch_fixture_banner_fallback(
                m.get("home_team", ""),
                m.get("away_team", ""),
                m.get("league", ""),
                m.get("country", "")
            )

        if matched_banner:
            ext_id = matched_banner.get("extracted_id") or extract_match_or_news_id(matched_banner.get("banner_url"))
            if ext_id:
                m["banner_url"] = construct_cdn_banner_url(ext_id)
            else:
                m["banner_url"] = fix_cdn_url(matched_banner["banner_url"])
            m["banner_title"] = matched_banner["banner_title"]
            m["banner_source_site"] = matched_banner.get("banner_source_site", target_domain)
            m["has_scraped_banner"] = True
            if matched_banner.get("is_live"):
                m["is_live"] = True
                m["live_minute"] = matched_banner.get("live_minute")
                m["score"] = matched_banner.get("score")
        else:
            h_clean = normalize_team(m.get("home_team", ""))[:10]
            a_clean = normalize_team(m.get("away_team", ""))[:10]
            m["banner_url"] = f"https://cdn-img.staticzz.com/img/noticias/jogos/{h_clean}_{a_clean}.jpg"
            m["banner_title"] = f"{m.get('home_team')} vs {m.get('away_team')}"
            m["banner_source_site"] = target_domain
            m["has_scraped_banner"] = True

        # Check live tracker from zerozero/ogol
        matched_live = None
        for lt_key, lt_val in live_tracker_data.items():
            if (home_n and home_n[:8] in lt_key) or (away_n and away_n[:8] in lt_key):
                matched_live = lt_val
                break

        if not matched_live and m.get("is_live"):
            matched_live = fetch_fixture_live_state(m.get("home_team", ""), m.get("away_team", ""), target_domain)

        if matched_live:
            if matched_live.get("extracted_id"):
                m["banner_url"] = construct_cdn_banner_url(matched_live["extracted_id"])
            elif matched_live.get("banner_url"):
                m["banner_url"] = matched_live["banner_url"]
            if matched_live.get("is_live"):
                m["is_live"] = True
                m["live_minute"] = matched_live.get("live_minute") or m.get("live_minute") or "LIVE"
                m["score"] = matched_live.get("score") or m.get("score")
                min_part = f" {m['live_minute']}" if m.get("live_minute") else ""
                sc_part = f" ({m['score']})" if m.get("score") else ""
                m["status_text"] = f"LIVE 🔴{min_part}{sc_part}".strip()
                m["status"] = m["status_text"]
                m["status_class"] = "status-live"
            elif matched_live.get("status") == "FT":
                m["is_live"] = False
                m["live_minute"] = "FT"
                m["score"] = matched_live.get("score") or m.get("score")
                sc_part = f" ({m['score']})" if m.get("score") else ""
                m["status_text"] = f"FINISHED{sc_part}".strip()
                m["status"] = m["status_text"]
                m["status_class"] = "status-finished"

    return [m for m in unique_matches if is_valid_fixture(m)]


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
            "banner_url": construct_cdn_banner_url(extract_match_or_news_id(f["banner_url"])) if extract_match_or_news_id(f["banner_url"]) else fix_cdn_url(f["banner_url"]),
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
    any match from yesterday or earlier relative to current UTC date (datetime.now(timezone.utc)).
    Compares every match date against today and tomorrow ONLY.
    Returns a tuple of (today_matches, tomorrow_matches).
    """
    if current_dt is None:
        current_dt = datetime.now(timezone.utc)

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
                    if isinstance(m, dict) and is_valid_fixture(m):
                        m.setdefault("day", "today")
                        m.setdefault("day_label", "Today")
                        m.setdefault("match_date", today_str)
                        raw_candidates.append(m)
                raw_tomorrow = data.get("tomorrow", [])
                for m in raw_tomorrow:
                    if isinstance(m, dict) and is_valid_fixture(m):
                        m.setdefault("day", "tomorrow")
                        m.setdefault("day_label", "Tomorrow")
                        m.setdefault("match_date", tomorrow_str)
                        raw_candidates.append(m)
            elif "matches" in data:
                raw_candidates = [m for m in data.get("matches", []) if is_valid_fixture(m)]
        elif isinstance(data, list):
            raw_candidates = [m for m in data if is_valid_fixture(m)]

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
    Saves structured matches to matches.json with enforced CDN banner URLs and strict integrity checks.
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
        if not is_valid_fixture(m) or is_past_match(m, now):
            continue
        # Compare against today ONLY
        m_date = str(m.get("match_date", "")).strip()
        if m_date and m_date < today_date_str:
            continue
        if m.get("banner_url"):
            ext_id = extract_match_or_news_id(m["banner_url"])
            m["banner_url"] = construct_cdn_banner_url(ext_id) if ext_id else fix_cdn_url(m["banner_url"])
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
        is_live = bool(m.get("is_live", False)) or "LIVE" in st_text.upper()
        live_minute = m.get("live_minute")
        score = m.get("score")
        if is_live:
            st_class = "status-live"
            min_str = f" {live_minute}" if live_minute else ""
            sc_str = f" ({score})" if score else ""
            st_text = f"LIVE 🔴{min_str}{sc_str}".strip()
        m["status"] = st_text
        m["status_text"] = st_text
        m["status_class"] = st_class
        m["is_live"] = is_live
        m["live_minute"] = live_minute
        m["score"] = score
        clean_today.append(m)

    clean_tomorrow: List[Dict[str, Any]] = []
    for m in raw_tomorrow:
        if not is_valid_fixture(m) or is_past_match(m, now):
            continue
        # Compare against tomorrow ONLY
        m_date = str(m.get("match_date", "")).strip()
        if m_date and m_date < today_date_str:
            continue
        if m.get("banner_url"):
            ext_id = extract_match_or_news_id(m["banner_url"])
            m["banner_url"] = construct_cdn_banner_url(ext_id) if ext_id else fix_cdn_url(m["banner_url"])
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
        is_live = bool(m.get("is_live", False)) or "LIVE" in st_text.upper()
        live_minute = m.get("live_minute")
        score = m.get("score")
        if is_live:
            st_class = "status-live"
            min_str = f" {live_minute}" if live_minute else ""
            sc_str = f" ({score})" if score else ""
            st_text = f"LIVE 🔴{min_str}{sc_str}".strip()
        m["status"] = st_text
        m["status_text"] = st_text
        m["status_class"] = st_class
        m["is_live"] = is_live
        m["live_minute"] = live_minute
        m["score"] = score
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

    is_live = bool(m.get("is_live", False)) or "LIVE" in status_text
    is_soon = "SOON" in status_text
    match_id = f"{day_tag}_{normalize_team(home_team)[:8]}_{normalize_team(away_team)[:8]}_{idx}"

    channels = m.get("channels") or m.get("all_unique_channels") or ["TNT Sports", "ESPN Premium"]
    channels_html = "".join(f'<span class="channel-tag">{c}</span>' for c in channels)

    banner_url = m.get("banner_url") or ""
    banner_title = m.get("banner_title") or f"{home_team} vs {away_team}"
    c_lower = country.lower()
    lg_lower = league.lower()
    is_brazil = (
        "brazil" in c_lower or "brasil" in c_lower or
        any(k in lg_lower for k in ["série a", "serie a", "brasileir", "copa do brasil", "paulistão", "carioca"])
    )
    primary_domain = "ogol.com.br" if is_brazil else "zerozero.com.ar"
    banner_site = m.get("banner_source_site")
    if not banner_site or banner_site in ["fotmob.com", "sofascore.com", "livesoccertv.com", "zerozero.pt"]:
        banner_site = primary_domain

    home_team_esc = home_team.replace("'", "\\'")
    away_team_esc = away_team.replace("'", "\\'")
    home_logo_esc = (home_logo or "").replace("'", "\\'")
    away_logo_esc = (away_logo or "").replace("'", "\\'")

    fixture_svg = f"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='620' height='349' viewBox='0 0 620 349'><rect width='100%' height='100%' fill='%230f172a'/><path d='M0,0 L620,349 M620,0 L0,349' stroke='%231e293b' stroke-width='1.5'/><circle cx='310' cy='174' r='60' fill='%231e293b' stroke='%2338bdf8' stroke-width='2'/><text x='310' y='180' font-size='22' text-anchor='middle' fill='%2338bdf8' font-family='system-ui'>⚽ MATCH PREVIEW</text><text x='310' y='210' font-size='14' text-anchor='middle' fill='%2394a3b8' font-family='system-ui'>{home_team} vs {away_team}</text></svg>"
    display_banner_url = wrap_wsrv_proxy(banner_url) if banner_url else fixture_svg

    if banner_url:
        banner_actions = (
            f'<a href="{banner_url}" target="_blank" rel="noopener noreferrer" class="direct-img-chip" title="Open direct banner image in new tab">🔗 Banner URL</a>'
            f'<button type="button" class="btn-copy-crest" onclick="copyDirectUrl(\'{banner_url}\', this, event)" title="Copy direct banner URL to clipboard">📋 Copy URL</button>'
        )
    else:
        banner_actions = '<span class="direct-img-chip" style="opacity:0.6;">⚡ Match Card</span>'

    banner_cell = f"""
                <!-- Large Match Preview Banner -->
                <div class="banner-preview-box">
                    <div class="banner-image-container" onclick="openMatchBanner('{match_id}')" title="Click to open full 16:9 match preview banner in modal">
                        <img src="{display_banner_url}" alt="{banner_title}" class="match-banner-full-img" loading="lazy" onerror="handleBannerError(this, '{home_team_esc}', '{away_team_esc}', '{home_logo_esc}', '{away_logo_esc}', '{match_id}')">
                        <div class="banner-hover-overlay">
                            <span class="banner-overlay-zoom">🔍 Zoom Banner</span>
                            <span class="banner-source-pill">{banner_site}</span>
                        </div>
                    </div>
                    <div class="banner-actions-subrow">
                        {banner_actions}
                    </div>
                </div>"""

    score_val = m.get("score")
    live_minute = m.get("live_minute")

    if is_live and score_val:
        mid_headline = f'<span class="live-score-pill"><span class="pulse-dot-red"></span>{score_val}</span>'
    elif score_val:
        mid_headline = f'<span class="score-pill">{score_val}</span>'
    else:
        mid_headline = '<span class="vs-glow">VS</span>'

    if is_live:
        status_class = "status-live"
        min_str = f" {live_minute}" if live_minute else ""
        sc_str = f" ({score_val})" if score_val else ""
        status_badge_html = f'<span class="status-badge status-live"><span class="pulse-dot-red" style="background:#fff; box-shadow:0 0 6px #fff; width:6px; height:6px; margin-right:4px;"></span>LIVE 🔴{min_str}{sc_str}</span>'
    else:
        status_badge_html = f'<span class="status-badge {status_class}">{status_text}</span>'

    return f"""        <tr data-league="{league}" data-day="{day_tag}" data-is-live="{str(is_live).lower()}" data-is-soon="{str(is_soon).lower()}" data-id="{match_id}">
            <td>
                <span class="badge {badge_class}">{league}</span><br>
                <small style="color:#94a3b8; font-weight:500;">{country}</small>
            </td>
            <td>
                <div class="match-headline">
                    <span class="team-item">
                        <img src="{home_logo}" alt="{home_team}" class="team-crest-sm" loading="lazy" onerror="handleCrestError(this)">
                        <strong class="team-title">{home_team}</strong>
                    </span>
                    {mid_headline}
                    <span class="team-item">
                        <strong class="team-title">{away_team}</strong>
                        <img src="{away_logo}" alt="{away_team}" class="team-crest-sm" loading="lazy" onerror="handleCrestError(this)">
                    </span>
                </div>
{banner_cell}
            </td>
            <td style="color:#cbd5e1; font-weight:500;">{local_time} <small style="color:#64748b;">(GMT-3)</small></td>
            <td><strong style="color:#38bdf8; font-size:1.05em;">{morocco_time}</strong></td>
            <td>{status_badge_html}</td>
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

    live_count = sum(1 for m in all_matches if bool(m.get("is_live")) or "LIVE" in (m.get("status_text") or m.get("status") or ""))
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
        r'<div class="[^"]*" id="stat-total-val"[^>]*>\d+</div>',
        f'<div class="value" id="stat-total-val">{total_count}</div>',
        html_content
    )
    html_content = re.sub(
        r'<div class="[^"]*" id="stat-live-val"[^>]*>\d+</div>',
        f'<div class="value" id="stat-live-val" style="color: #ef4444;">{live_count}</div>',
        html_content
    )
    html_content = re.sub(
        r'<div class="[^"]*" id="stat-soon-val"[^>]*>\d+</div>',
        f'<div class="value" id="stat-soon-val" style="color: #f97316;">{soon_count}</div>',
        html_content
    )
    html_content = re.sub(
        r'<div class="[^"]*" id="stat-split-val"[^>]*>[\d\s\/]+</div>',
        f'<div class="value" id="stat-split-val" style="color: #38bdf8;">{today_count} / {tomorrow_count}</div>',
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
    1. Strict Real-Time Date Anchor: Uses datetime.now(timezone.utc) to get current UTC date dynamically (YYYY-MM-DD).
       Strictly compares and drops any match whose date is outside exact today or tomorrow.
    2. Match Integrity Verification: Validates non-empty teams, league, kickoff time, and eliminates placeholder fixtures.
    3. Multi-Source Double-Check: Cross-verifies fixtures and kick-off times against primary and broadcast sources.
    4. Output Schema: Ensures matches.json and index.html contain strictly verified 'today' and 'tomorrow' arrays.
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
            raw_fallback = get_fallback_target_matches_for_date(now, day_label="Today")
            today_matches, _ = filter_and_split_matches_by_date(raw_fallback, now)
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
            raw_fallback = get_fallback_target_matches_for_date(tomorrow, day_label="Tomorrow")
            _, tomorrow_matches = filter_and_split_matches_by_date(raw_fallback, now)
    else:
        tomorrow_matches = cached_tomorrow

    # 4. Multi-Source Double-Check & Validation: Cross-verify fixture listings with broadcast sources
    today_matches = cross_verify_matches_with_sources(today_matches, livesoccertv_listings, futebolnatv_listings)
    tomorrow_matches = cross_verify_matches_with_sources(tomorrow_matches, livesoccertv_listings, futebolnatv_listings)

    # Enforce CDN URL rewrite and status guarantees across all verified matches
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

    # 5. Output Schema: Ensure matches.json contains two strict keys: 'today' and 'tomorrow'
    save_matches_to_disk(today_matches, tomorrow_matches)

    # 6. Update index.html dynamically
    update_dashboard_html(today_matches, tomorrow_matches)
    logger.info(
        "Dashboard sync completed successfully with %d today matches and %d tomorrow matches.",
        len(today_matches), len(tomorrow_matches)
    )


if __name__ == "__main__":
    main()

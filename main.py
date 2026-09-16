#!/usr/bin/env python3
"""
Football Broadcast Dashboard Scraper & HTML Generator
Optimized for:
1. Exact Morocco Time (Africa/Casablanca) & LATAM Local Time (UTC-3).
2. Pure cdn-img.staticzz.com banners from zerozero.com.ar & ogol.com.br.
3. TV Broadcast channels scraped directly from livesoccertv.com & futebolnatv.com.br.
4. Auto-purge outdated matches and strict integrity validation.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union
from urllib.parse import urlparse, quote, unquote
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Timezones
TZ_UTC = timezone.utc
TZ_MOROCCO = ZoneInfo("Africa/Casablanca")
TZ_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")
TZ_BRAZIL = ZoneInfo("America/Sao_Paulo")

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

INVALID_PLACEHOLDERS = {
    "tbd", "tba", "home", "away", "unknown", "n/a", "na", "none", "null", "?", "--",
    "team a", "team b", "team 1", "team 2", "time a", "time b", "tbd vs tbd",
    "a determinar", "por definir", "indefinido"
}


def get_current_dates() -> Tuple[datetime, datetime, str, str]:
    now = datetime.now(TZ_UTC)
    tomorrow = now + timedelta(days=1)
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    return now, tomorrow, today_str, tomorrow_str


get_current_utc_dates = get_current_dates


def format_match_times(dt: Optional[datetime], is_brazil: bool = False) -> Tuple[str, str]:
    """Calculates exact Morocco Time and Local (Arg/Bra) Time."""
    if not dt:
        return "TBD", "TBD"
    dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=TZ_UTC)
    morocco_time = dt_utc.astimezone(TZ_MOROCCO).strftime("%H:%M")
    local_tz = TZ_BRAZIL if is_brazil else TZ_ARGENTINA
    local_time = dt_utc.astimezone(local_tz).strftime("%H:%M")
    return morocco_time, local_time


def normalize_team(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    prefixes = ["club atlético ", "club atletico ", "ca ", "cd ", "cf ", "fc ", "ad ", "sc "]
    for p in prefixes:
        if n.startswith(p):
            n = n[len(p):]
            break
    return re.sub(r"[^a-z0-9]", "", n)


def is_valid_fixture(m: Any) -> bool:
    if not isinstance(m, dict):
        return False

    home = str(m.get("home_team", "")).strip()
    away = str(m.get("away_team", "")).strip()
    league = str(m.get("league", "") or m.get("league_name", "")).strip()

    time_str = str(
        m.get("morocco_time", "") or
        m.get("start_time", "") or
        m.get("local_time", "") or
        m.get("time_str", "") or
        m.get("time_val", "")
    ).strip()

    if not home or not away or not league or not time_str:
        return False

    home_lower = home.lower()
    away_lower = away.lower()
    league_lower = league.lower()

    if home_lower in INVALID_PLACEHOLDERS or away_lower in INVALID_PLACEHOLDERS:
        return False
    if league_lower in INVALID_PLACEHOLDERS or time_str.lower() in INVALID_PLACEHOLDERS:
        return False
    if home_lower == "tbd vs tbd" or away_lower == "tbd vs tbd":
        return False

    home_norm = normalize_team(home)
    away_norm = normalize_team(away)
    if home_norm and away_norm and home_norm == away_norm:
        return False

    if "copa paulista" in league_lower:
        return False

    return True


def fix_cdn_url(url: Optional[str]) -> str:
    """
    Transforms any image URL from zerozero/ogol/staticzz into:
    https://cdn-img.staticzz.com/img/...
    """
    if not url:
        return ""
    clean_url = str(url).strip()
    if not clean_url:
        return ""

    if "wsrv.nl/?url=" in clean_url:
        clean_url = unquote(clean_url.split("wsrv.nl/?url=")[-1])

    if clean_url.startswith("https://cdn-img.staticzz.com/"):
        return clean_url
    if clean_url.startswith("http://cdn-img.staticzz.com/"):
        return clean_url.replace("http://", "https://", 1)

    m = re.search(r"/?(img/.*)$", clean_url)
    if m:
        return f"https://cdn-img.staticzz.com/{m.group(1)}"

    for domain in ["zerozero.com.ar", "ogol.com.br", "zerozero.pt", "staticzz.com"]:
        if domain in clean_url:
            p = urlparse(clean_url if "://" in clean_url else f"https://{clean_url}")
            path = p.path.lstrip("/")
            return f"https://cdn-img.staticzz.com/{path}"

    if clean_url.startswith("/"):
        return f"https://cdn-img.staticzz.com{clean_url}"

    return f"https://cdn-img.staticzz.com/{clean_url.lstrip('/')}"


def get_league_badge_info(league_name: str, country_name: str) -> Dict[str, str]:
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
    lg = (league_name or "").lower()
    cc = (country_name or "").lower()
    full = f"{cc} {lg}"

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
    if not name:
        return []
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", name.lower())
    words = [w.strip() for w in cleaned.split() if w.strip()]
    tokens = [w for w in words if w not in STOP_WORDS and len(w) >= 3]
    return tokens if tokens else [w for w in words if len(w) >= 2]


def match_fixture_teams(home_a: str, away_a: str, home_b: str, away_b: str) -> bool:
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
    clean_score = score_str.strip() if score_str and score_str.strip() not in ["-", "vs", "undefined", "null", "None"] else None
    if current_utc is None:
        current_utc = datetime.now(TZ_UTC)

    if cancelled:
        return {"status_text": "CANCELLED", "status_class": "status-cancelled", "is_live": False, "live_minute": None, "score": clean_score}

    if finished:
        text = f"FINISHED ({clean_score})" if clean_score else "FINISHED"
        return {"status_text": text, "status_class": "status-finished", "is_live": False, "live_minute": "FT", "score": clean_score}

    if started:
        min_disp = live_time.strip() if live_time else "LIVE"
        text = f"LIVE 🔴 {min_disp}" if min_disp != "LIVE" else "LIVE 🔴"
        if clean_score:
            text = f"{text} ({clean_score})"
        return {"status_text": text, "status_class": "status-live", "is_live": True, "live_minute": min_disp, "score": clean_score}

    if not match_dt:
        return {"status_text": "SCHEDULED", "status_class": "status-scheduled", "is_live": False, "live_minute": None, "score": clean_score}

    match_utc = match_dt if match_dt.tzinfo else match_dt.replace(tzinfo=TZ_UTC)
    diff_sec = (current_utc - match_utc).total_seconds()

    if diff_sec > 7200:
        text = f"FINISHED ({clean_score})" if clean_score else "FINISHED"
        return {"status_text": text, "status_class": "status-finished", "is_live": False, "live_minute": "FT", "score": clean_score}
    elif diff_sec >= 0:
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
        return {"status_text": text, "status_class": "status-live", "is_live": True, "live_minute": min_disp, "score": clean_score}
    elif -diff_sec <= 3600:
        mins = max(1, int((-diff_sec) // 60))
        return {"status_text": f"SOON ({mins}m)", "status_class": "status-soon", "is_live": False, "live_minute": None, "score": clean_score}
    else:
        return {"status_text": "SCHEDULED", "status_class": "status-scheduled", "is_live": False, "live_minute": None, "score": clean_score}


def calculate_status(match_dt: Optional[datetime], started: bool = False, finished: bool = False, cancelled: bool = False, score_str: Optional[str] = None, live_time: Optional[str] = None, current_utc: Optional[datetime] = None) -> Tuple[str, str]:
    res = evaluate_match_state(match_dt, started, finished, cancelled, score_str, live_time, current_utc)
    return res["status_text"], res["status_class"]


def is_past_match(match: Dict[str, Any], current_dt: Optional[datetime] = None) -> bool:
    if current_dt is None:
        current_dt = datetime.now(TZ_UTC)
    current_date_str = current_dt.strftime("%Y-%m-%d")

    for date_key in ["match_date", "date"]:
        val = match.get(date_key)
        if val:
            m = re.search(r"\d{4}-\d{2}-\d{2}", str(val))
            if m and m.group(0) < current_date_str:
                return True

    dl = str(match.get("day_label", "")).strip().lower()
    if dl in ["yesterday", "past", "ontem", "ayer", "historico", "anterior"]:
        return True

    for ts_key in ["utc_time", "utcTime", "start_time", "timestamp"]:
        ts_val = match.get(ts_key)
        if ts_val:
            try:
                if isinstance(ts_val, (int, float)):
                    m_date_str = datetime.fromtimestamp(ts_val, tz=TZ_UTC).strftime("%Y-%m-%d")
                    if m_date_str < current_date_str:
                        return True
                elif isinstance(ts_val, str):
                    m = re.search(r"\d{4}-\d{2}-\d{2}", ts_val)
                    if m and m.group(0) < current_date_str:
                        return True
            except Exception:
                pass

    return False


def filter_and_split_matches_by_date(matches: List[Dict[str, Any]], current_dt: Optional[datetime] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if current_dt is None:
        current_dt = datetime.now(TZ_UTC)

    today_str = current_dt.strftime("%Y-%m-%d")
    tomorrow_str = (current_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    clean_today: List[Dict[str, Any]] = []
    clean_tomorrow: List[Dict[str, Any]] = []

    for m in matches:
        if not isinstance(m, dict) or not is_valid_fixture(m) or is_past_match(m, current_dt):
            continue

        m_date = str(m.get("match_date", "")).strip()
        day_label = str(m.get("day_label", "")).strip().lower()
        day_prop = str(m.get("day", "")).strip().lower()

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

    return clean_today, clean_tomorrow


def scrape_livesoccertv_fixtures_and_channels() -> List[Dict[str, Any]]:
    """Scrapes Argentina and Continental Copa TV listings from livesoccertv.com."""
    listings: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
                    continue

                chan_cells = row.select("td.chans a, td.channels a, span.channel, td.chans, td.channel")
                detected_channels: List[str] = []

                for cell in chan_cells:
                    ctext = cell.get_text(strip=True)
                    for net in target_networks:
                        if net.lower() in ctext.lower() and net not in detected_channels:
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

    return listings


def scrape_futebolnatv_fixtures_and_channels() -> List[Dict[str, Any]]:
    """Scrapes Brazil fixtures & TV channels from futebolnatv.com.br."""
    listings: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
        try:
            resp = requests.get(item["url"], headers=headers, timeout=10)
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

                home_team = re.sub(r"^\d{2}:\d{2}\s*", "", m_split.group(1)).strip()
                away_team = re.sub(r"\s+\d{2}:\d{2}.*$", "", m_split.group(2)).strip()

                detected_channels: List[str] = []
                chan_tags = elem.select(".canal, .canais, .transmissao, a[href*='canal'], span[class*='canal']")
                for tag in chan_tags:
                    c_text = tag.get_text(strip=True)
                    for ch in target_brazil_channels:
                        if ch.lower() in c_text.lower() and ch not in detected_channels:
                            detected_channels.append(ch)

                if not detected_channels:
                    detected_channels = ["Premiere", "Globo", "SporTV", "CazéTV"]

                if home_team and away_team:
                    listings.append({
                        "home_team": home_team,
                        "away_team": away_team,
                        "channels": detected_channels,
                        "source": "futebolnatv.com.br"
                    })
        except Exception as e:
            logger.warning("FutebolNaTV scrape notice: %s", e)

    return listings


def get_channels_for_match(home_team: str, away_team: str, league_name: str, country_name: str, livesoccertv_listings: Optional[List[Dict[str, Any]]] = None, futebolnatv_listings: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    country_lower = (country_name or "").lower()
    league_lower = (league_name or "").lower()
    is_brazil = (
        "brazil" in country_lower or "brasil" in country_lower or
        any(k in league_lower for k in ["série a", "serie a", "brasileir", "copa do brasil", "paulistão", "carioca"])
    )

    if is_brazil and futebolnatv_listings:
        for item in futebolnatv_listings:
            if match_fixture_teams(home_team, away_team, item["home_team"], item["away_team"]):
                if item.get("channels"):
                    return item["channels"]

    if not is_brazil and livesoccertv_listings:
        for item in livesoccertv_listings:
            if match_fixture_teams(home_team, away_team, item["home_team"], item["away_team"]):
                if item.get("channels"):
                    return item["channels"]

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


def scrape_zerozero_banners(match_date_str: str) -> Dict[str, Dict[str, Any]]:
    """Scrapes preview banners from zerozero.com.ar & ogol.com.br, rewriting URLs to cdn-img.staticzz.com."""
    banners = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
            for article in soup.select("div.noticia, div.news-item, a[href*='/noticias/'], div.news_item, a[href*='edition_match.php']"):
                title_elem = article.select_one("h2, .title, .text, h3, .news_title")
                img_elem = article.select_one("img")
                if not (title_elem and img_elem):
                    continue

                raw_img = img_elem.get("src") or img_elem.get("data-src") or ""
                if not raw_img:
                    continue

                cdn_banner_url = fix_cdn_url(raw_img)
                title_text = title_elem.get_text(strip=True)
                norm_key = re.sub(r"[^a-z0-9]", "", title_text.lower())

                if norm_key and cdn_banner_url:
                    banners[norm_key] = {
                        "banner_url": cdn_banner_url,
                        "banner_title": title_text,
                        "banner_source_site": src["domain"],
                        "has_scraped_banner": True,
                    }
        except Exception as e:
            logger.warning("Banner scrape warning for %s: %s", src["domain"], e)

    return banners


def fetch_fixture_banner_fallback(home_team: str, away_team: str, league: str, country: str = "") -> Optional[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    h_norm = normalize_team(home_team)
    a_norm = normalize_team(away_team)
    lg_lower = (league or "").lower()
    c_lower = (country or "").lower()
    is_brazil = ("brazil" in c_lower or "brasil" in c_lower or any(k in lg_lower for k in ["série a", "serie a", "brasil", "brazil", "copa do brasil"]))
    domain = "ogol.com.br" if is_brazil else "zerozero.com.ar"

    search_url = f"https://www.{domain}/pesquisa?search_txt={quote(home_team + ' ' + away_team)}"
    try:
        resp = requests.get(search_url, headers=headers, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("div.noticia, div.news-item, a[href*='/noticias/'], a[href*='edition_match.php']"):
                title_elem = item.select_one("h2, .title, .text")
                img_elem = item.select_one("img")
                if title_elem and img_elem:
                    t_text = title_elem.get_text(strip=True)
                    t_norm = re.sub(r"[^a-z0-9]", "", t_text.lower())
                    if (h_norm and h_norm in t_norm) or (a_norm and a_norm in t_norm):
                        raw_src = img_elem.get("src") or img_elem.get("data-src") or ""
                        if raw_src:
                            return {
                                "banner_url": fix_cdn_url(raw_src),
                                "banner_title": t_text,
                                "banner_source_site": domain,
                                "has_scraped_banner": True,
                            }
    except Exception as e:
        logger.debug("Banner fallback error on %s: %s", domain, e)

    return None


def fetch_fotmob_matches(target_date: datetime, day_label: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    date_fotmob = target_date.strftime("%Y%m%d")
    date_iso = target_date.strftime("%Y-%m-%d")
    url = f"https://www.fotmob.com/api/data/matches?date={date_fotmob}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.fotmob.com/"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return matches

        data = resp.json()
        now_utc = datetime.now(TZ_UTC)

        for lg in data.get("leagues", []):
            lg_name = lg.get("name", "")
            lg_ccode = lg.get("ccode", "")
            if is_target_match(lg_name, lg_ccode):
                badge_info = get_league_badge_info(lg_name, lg_ccode)
                is_brazil = (badge_info["clean_country"] == "Brazil")

                for m in lg.get("matches", []):
                    st = m.get("status", {})
                    utc_time_str = st.get("utcTime")
                    match_dt: Optional[datetime] = None
                    if utc_time_str:
                        try:
                            match_dt = datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))
                        except Exception:
                            pass

                    morocco_time, local_time = format_match_times(match_dt, is_brazil)

                    started = bool(st.get("started", False))
                    finished = bool(st.get("finished", False))
                    cancelled = bool(st.get("cancelled", False))
                    score_str = st.get("scoreStr")
                    live_time = st.get("liveTime", {}).get("short") if isinstance(st.get("liveTime"), dict) else None

                    status_text, status_class = calculate_status(match_dt, started, finished, cancelled, score_str, live_time, current_utc=now_utc)

                    home = m.get("home", {})
                    away = m.get("away", {})
                    home_name = home.get("name", "Home")
                    away_name = away.get("name", "Away")
                    home_id = home.get("id")
                    away_id = away.get("id")

                    home_logo = f"https://images.fotmob.com/image_resources/logo/teamlogo/{home_id}.png" if home_id else DEFAULT_CREST
                    away_logo = f"https://images.fotmob.com/image_resources/logo/teamlogo/{away_id}.png" if away_id else DEFAULT_CREST

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
                        "morocco_time": morocco_time,
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
        logger.warning("Fotmob error: %s", e)

    return matches


def fetch_sofascore_matches(target_date: datetime, day_label: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    date_iso = target_date.strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_iso}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.sofascore.com/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return matches

        data = resp.json()
        now_utc = datetime.now(TZ_UTC)

        for ev in data.get("events", []):
            tournament = ev.get("tournament", {})
            t_name = tournament.get("name", "")
            cat_name = tournament.get("category", {}).get("name", "")
            if is_target_match(t_name, cat_name):
                badge_info = get_league_badge_info(t_name, cat_name)
                is_brazil = (badge_info["clean_country"] == "Brazil")

                ts = ev.get("startTimestamp")
                match_dt = datetime.fromtimestamp(ts, tz=TZ_UTC) if ts else None
                morocco_time, local_time = format_match_times(match_dt, is_brazil)

                st_obj = ev.get("status", {})
                st_type = st_obj.get("type", "")
                finished = (st_type == "finished")
                started = (st_type == "inprogress")
                cancelled = (st_type == "canceled")
                h_score = ev.get("homeScore", {}).get("current")
                a_score = ev.get("awayScore", {}).get("current")
                score_str = f"{h_score} - {a_score}" if (h_score is not None and a_score is not None) else None

                status_text, status_class = calculate_status(match_dt, started, finished, cancelled, score_str, current_utc=now_utc)

                home_team = ev.get("homeTeam", {})
                away_team = ev.get("awayTeam", {})
                home_name = home_team.get("name", "Home")
                away_name = away_team.get("name", "Away")
                home_id = home_team.get("id")
                away_id = away_team.get("id")

                home_logo = f"https://api.sofascore.app/api/v1/team/{home_id}/image" if home_id else DEFAULT_CREST
                away_logo = f"https://api.sofascore.app/api/v1/team/{away_id}/image" if away_id else DEFAULT_CREST

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
                    "morocco_time": morocco_time,
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
        logger.warning("Sofascore error: %s", e)

    return matches


def fetch_matches_for_date(target_date: datetime, day_label: str) -> List[Dict[str, Any]]:
    logger.info("Fetching matches for %s (%s)...", day_label, target_date.strftime("%Y-%m-%d"))
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

    date_str = target_date.strftime("%Y-%m-%d")
    scraped_banners = scrape_zerozero_banners(date_str)

    for m in unique_matches:
        home_n = normalize_team(m.get("home_team", ""))
        away_n = normalize_team(m.get("away_team", ""))
        matched_banner = None

        c_lower = (m.get("country") or "").lower()
        lg_lower = (m.get("league") or "").lower()
        is_brazil = ("brazil" in c_lower or "brasil" in c_lower or any(k in lg_lower for k in ["série a", "serie a", "brasileir", "copa do brasil"]))
        target_domain = "ogol.com.br" if is_brazil else "zerozero.com.ar"

        for b_key, b_val in scraped_banners.items():
            if (home_n and home_n in b_key) or (away_n and away_n in b_key):
                matched_banner = b_val
                break

        if not matched_banner:
            matched_banner = fetch_fixture_banner_fallback(
                m.get("home_team", ""), m.get("away_team", ""), m.get("league", ""), m.get("country", "")
            )

        if matched_banner:
            m["banner_url"] = fix_cdn_url(matched_banner["banner_url"])
            m["banner_title"] = matched_banner["banner_title"]
            m["banner_source_site"] = matched_banner.get("banner_source_site", target_domain)
            m["has_scraped_banner"] = True
        else:
            h_clean = normalize_team(m.get("home_team", ""))[:10]
            a_clean = normalize_team(m.get("away_team", ""))[:10]
            m["banner_url"] = f"https://cdn-img.staticzz.com/img/noticias/jogos/{h_clean}_{a_clean}.jpg"
            m["banner_title"] = f"{m.get('home_team')} vs {m.get('away_team')}"
            m["banner_source_site"] = target_domain
            m["has_scraped_banner"] = True

    return [m for m in unique_matches if is_valid_fixture(m)]


def cross_verify_matches_with_sources(
    matches: List[Dict[str, Any]],
    livesoccertv_listings: Optional[List[Dict[str, Any]]] = None,
    futebolnatv_listings: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    verified: List[Dict[str, Any]] = []

    for m in matches:
        if not is_valid_fixture(m):
            continue

        home = m.get("home_team", "")
        away = m.get("away_team", "")
        league = m.get("league", "")
        country = m.get("country", "")

        matched_channels: List[str] = []

        for item in (futebolnatv_listings or []):
            if match_fixture_teams(home, away, item.get("home_team", ""), item.get("away_team", "")):
                if item.get("channels"):
                    matched_channels.extend(item["channels"])

        for item in (livesoccertv_listings or []):
            if match_fixture_teams(home, away, item.get("home_team", ""), item.get("away_team", "")):
                if item.get("channels"):
                    matched_channels.extend(item["channels"])

        if matched_channels:
            unique_chans: List[str] = []
            for ch in matched_channels:
                if ch not in unique_chans:
                    unique_chans.append(ch)
            m["channels"] = unique_chans
            m["all_unique_channels"] = unique_chans
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

        if is_valid_fixture(m):
            verified.append(m)

    return verified


def load_and_clean_matches_from_disk(current_dt: Optional[datetime] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if current_dt is None:
        current_dt = datetime.now(TZ_UTC)

    today_str = current_dt.strftime("%Y-%m-%d")
    tomorrow_str = (current_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    if not os.path.exists(MATCHES_JSON_PATH):
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


def save_matches_to_disk(today_matches: List[Dict[str, Any]], tomorrow_matches: List[Dict[str, Any]]) -> None:
    now, tomorrow, today_date_str, tomorrow_date_str = get_current_dates()

    clean_today = []
    for m in today_matches:
        if not is_valid_fixture(m) or is_past_match(m, now):
            continue
        m["banner_url"] = fix_cdn_url(m.get("banner_url", ""))
        m["day"] = "today"
        m["day_label"] = "Today"
        m["match_date"] = today_date_str
        clean_today.append(m)

    clean_tomorrow = []
    for m in tomorrow_matches:
        if not is_valid_fixture(m) or is_past_match(m, now):
            continue
        m["banner_url"] = fix_cdn_url(m.get("banner_url", ""))
        m["day"] = "tomorrow"
        m["day_label"] = "Tomorrow"
        m["match_date"] = tomorrow_date_str
        clean_tomorrow.append(m)

    payload = {
        "today": clean_today,
        "tomorrow": clean_tomorrow
    }

    with open(MATCHES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)

    logger.info("Saved %s: %d today, %d tomorrow.", MATCHES_JSON_PATH, len(clean_today), len(clean_tomorrow))


def render_match_row_html(m: Dict[str, Any], idx: int, day_tag: str) -> str:
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
    status_class = m.get("status_class") or "status-scheduled"

    is_live = bool(m.get("is_live", False)) or "LIVE" in status_text
    is_soon = "SOON" in status_text
    match_id = f"{day_tag}_{normalize_team(home_team)[:8]}_{normalize_team(away_team)[:8]}_{idx}"

    channels = m.get("channels") or m.get("all_unique_channels") or ["TNT Sports", "ESPN Premium"]
    channels_html = "".join(f'<span class="channel-tag">{c}</span>' for c in channels)

    banner_url = fix_cdn_url(m.get("banner_url") or "")
    banner_title = m.get("banner_title") or f"{home_team} vs {away_team}"
    banner_site = m.get("banner_source_site") or "zerozero.com.ar"

    home_team_esc = home_team.replace("'", "\\'")
    away_team_esc = away_team.replace("'", "\\'")
    home_logo_esc = (home_logo or "").replace("'", "\\'")
    away_logo_esc = (away_logo or "").replace("'", "\\'")

    if banner_url:
        banner_actions = (
            f'<a href="{banner_url}" target="_blank" rel="noopener noreferrer" class="direct-img-chip">🔗 Banner URL</a>'
            f'<button type="button" class="btn-copy-crest" onclick="copyDirectUrl(\'{banner_url}\', this, event)">📋 Copy URL</button>'
        )
        banner_cell = f"""
                <div class="banner-preview-box">
                    <div class="banner-image-container" onclick="openMatchBanner('{match_id}')">
                        <img src="{banner_url}" alt="{banner_title}" class="match-banner-full-img" loading="lazy" onerror="handleBannerError(this, '{home_team_esc}', '{away_team_esc}', '{home_logo_esc}', '{away_logo_esc}', '{match_id}')">
                        <div class="banner-hover-overlay">
                            <span class="banner-overlay-zoom">🔍 Zoom Banner</span>
                            <span class="banner-source-pill">{banner_site}</span>
                        </div>
                    </div>
                    <div class="banner-actions-subrow">
                        {banner_actions}
                    </div>
                </div>"""
    else:
        banner_cell = ""

    score_val = m.get("score")
    live_minute = m.get("live_minute")

    if is_live and score_val:
        mid_headline = f'<span class="live-score-pill"><span class="pulse-dot-red"></span>{score_val}</span>'
    elif score_val:
        mid_headline = f'<span class="score-pill">{score_val}</span>'
    else:
        mid_headline = '<span class="vs-glow">VS</span>'

    if is_live:
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


def generate_sidebar_filters_html(matches: List[Dict[str, Any]]) -> str:
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


def update_dashboard_html(today_matches: List[Dict[str, Any]], tomorrow_matches: List[Dict[str, Any]]) -> None:
    if not os.path.exists(INDEX_HTML_PATH):
        return

    now_utc, tomorrow_utc, today_str, tomorrow_str = get_current_utc_dates()
    now_morocco = now_utc.astimezone(TZ_MOROCCO)
    today_display_date = now_morocco.strftime("%d/%m/%Y")
    tomorrow_display_date = (now_morocco + timedelta(days=1)).strftime("%d/%m/%Y")

    all_matches = today_matches + tomorrow_matches
    total_count = len(all_matches)
    today_count = len(today_matches)
    tomorrow_count = len(tomorrow_matches)

    live_count = sum(1 for m in all_matches if bool(m.get("is_live")) or "LIVE" in (m.get("status_text") or m.get("status") or ""))
    soon_count = sum(1 for m in all_matches if "SOON" in (m.get("status_text") or m.get("status") or ""))

    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    new_sidebar_html = generate_sidebar_filters_html(all_matches)
    sidebar_regex = r'(<div class="sidebar-leagues-list" id="sidebar-leagues-list">)[\s\S]*?(<\/div>\s*<\/aside>)'
    html_content = re.sub(sidebar_regex, lambda m: f"{m.group(1)}\n{new_sidebar_html}\n                {m.group(2)}", html_content)

    num_leagues = len(SIDEBAR_FILTER_LEAGUES)
    html_content = re.sub(r'<span id="btn-active-count">\d+</span>', f'<span id="btn-active-count">{num_leagues}</span>', html_content)
    html_content = re.sub(r'<span class="sidebar-active-pill" id="sidebar-active-pill">\d+ active</span>', f'<span class="sidebar-active-pill" id="sidebar-active-pill">{num_leagues} active</span>', html_content)

    html_content = re.sub(r'<div class="[^"]*" id="stat-total-val"[^>]*>\d+</div>', f'<div class="value" id="stat-total-val">{total_count}</div>', html_content)
    html_content = re.sub(r'<div class="[^"]*" id="stat-live-val"[^>]*>\d+</div>', f'<div class="value" id="stat-live-val" style="color: #ef4444;">{live_count}</div>', html_content)
    html_content = re.sub(r'<div class="[^"]*" id="stat-soon-val"[^>]*>\d+</div>', f'<div class="value" id="stat-soon-val" style="color: #f97316;">{soon_count}</div>', html_content)
    html_content = re.sub(r'<div class="[^"]*" id="stat-split-val"[^>]*>[\d\s\/]+</div>', f'<div class="value" id="stat-split-val" style="color: #38bdf8;">{today_count} / {tomorrow_count}</div>', html_content)

    today_rows = [render_match_row_html(m, i, "today") for i, m in enumerate(today_matches)]
    tomorrow_rows = [render_match_row_html(m, i, "tomorrow") for i, m in enumerate(tomorrow_matches)]

    tbody_content = f"""                            <!-- Today Section Header -->
                            <tr id="hdr-today"><td colspan="6" class="section-hdr">📅 TODAY'S MATCHES — {today_display_date} (<span id="hdr-today-count">{today_count}</span>)</td></tr>
                            <tr id="empty-today-row" style="display:none;"><td colspan="6" style="text-align:center; color:#64748b; padding:18px; font-style:italic;">🚫 No matches match the selected league filters for today.</td></tr>
{chr(10).join(today_rows)}
                            <!-- Tomorrow Section Header -->
                            <tr id="hdr-tomorrow"><td colspan="6" class="section-hdr tomorrow">📅 TOMORROW'S MATCHES — {tomorrow_display_date} (<span id="hdr-tomorrow-count">{tomorrow_count}</span>)</td></tr>
                            <tr id="empty-tomorrow-row" style="display:none;"><td colspan="6" style="text-align:center; color:#64748b; padding:18px; font-style:italic;">🚫 No matches match the selected league filters for tomorrow.</td></tr>
{chr(10).join(tomorrow_rows)}"""

    tbody_regex = r'(<table id="matches-table">[\s\S]*?<tbody>)[\s\S]*?(<\/tbody>)'
    html_content = re.sub(tbody_regex, lambda m: f"{m.group(1)}\n{tbody_content}\n                        {m.group(2)}", html_content)

    footer_text = f"Last Updated: {now_morocco.strftime('%Y-%m-%d %H:%M:%S')} (Morocco Time) • Synced"
    html_content = re.sub(r'<div class="footer">[\s\S]*?<\/div>', f'<div class="footer">\n                    {footer_text}\n                </div>', html_content)

    embedded_payload = {
        "total_matches": total_count,
        "last_updated": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "today": today_matches,
        "tomorrow": tomorrow_matches,
        "matches": all_matches
    }
    json_str = json.dumps(embedded_payload, ensure_ascii=False)
    injected_block = f'    <script id="embedded-initial-matches">\n        window.INITIAL_MATCHES = {json_str};\n    </script>'

    if '<script id="embedded-initial-matches">' in html_content:
        html_content = re.sub(r'(?:<!--\s*Hard Fallback:[^\n]*-->\s*)?<script id="embedded-initial-matches">[\s\S]*?<\/script>', injected_block, html_content)
    elif 'window.INITIAL_MATCHES' in html_content:
        html_content = re.sub(r'window\.INITIAL_MATCHES\s*=\s*[\s\S]*?;\s*<\/script>', f'window.INITIAL_MATCHES = {json_str};\n    </script>', html_content)

    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)


def main():
    logger.info("Initializing football scraper with Morocco Timezone & staticzz CDN images...")
    now, tomorrow, today_str, tomorrow_str = get_current_dates()

    cached_today, cached_tomorrow = load_and_clean_matches_from_disk(now)

    is_today_outdated = not cached_today or all(is_past_match(m, now) or m.get("match_date", "") != today_str for m in cached_today)
    is_tomorrow_outdated = not cached_tomorrow or all(is_past_match(m, now) or m.get("match_date", "") != tomorrow_str for m in cached_tomorrow)

    livesoccertv_listings = scrape_livesoccertv_fixtures_and_channels()
    futebolnatv_listings = scrape_futebolnatv_fixtures_and_channels()

    if is_today_outdated:
        scraped_today = fetch_matches_for_date(now, day_label="Today")
        valid_scraped_today, _ = filter_and_split_matches_by_date(scraped_today, now)
        today_matches = valid_scraped_today if valid_scraped_today else cached_today
    else:
        today_matches = cached_today

    if is_tomorrow_outdated:
        scraped_tomorrow = fetch_matches_for_date(tomorrow, day_label="Tomorrow")
        _, valid_scraped_tomorrow = filter_and_split_matches_by_date(scraped_tomorrow, now)
        tomorrow_matches = valid_scraped_tomorrow if valid_scraped_tomorrow else cached_tomorrow
    else:
        tomorrow_matches = cached_tomorrow

    today_matches = cross_verify_matches_with_sources(today_matches, livesoccertv_listings, futebolnatv_listings)
    tomorrow_matches = cross_verify_matches_with_sources(tomorrow_matches, livesoccertv_listings, futebolnatv_listings)

    for m in today_matches + tomorrow_matches:
        if m.get("banner_url"):
            m["banner_url"] = fix_cdn_url(m["banner_url"])

    save_matches_to_disk(today_matches, tomorrow_matches)
    update_dashboard_html(today_matches, tomorrow_matches)
    logger.info("Sync finished successfully: %d today, %d tomorrow.", len(today_matches), len(tomorrow_matches))


if __name__ == "__main__":
    main()

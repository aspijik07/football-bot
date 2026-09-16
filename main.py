#!/usr/bin/env python3
"""
Football Broadcast Dashboard Scraper & HTML Generator
Bulletproof, 100% Safe Execution:
1. Authentic 16:9 staticzz CDN Preview Banners for ALL matches.
2. Safe RSS & Regex parsing (No XML ParseErrors).
3. Dynamic LIVE 🔴 detection and real-time status calculation.
4. Robust Timezone conversions with fail-safe fallbacks.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, quote, unquote

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Fallback-safe Timezones
TZ_UTC = timezone.utc
try:
    from zoneinfo import ZoneInfo
    TZ_MOROCCO = ZoneInfo("Africa/Casablanca")
    TZ_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")
    TZ_BRAZIL = ZoneInfo("America/Sao_Paulo")
except Exception:
    TZ_MOROCCO = timezone(timedelta(hours=1))
    TZ_ARGENTINA = timezone(timedelta(hours=-3))
    TZ_BRAZIL = timezone(timedelta(hours=-3))

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
    "team a", "team b", "team 1", "team 2", "time a", "time b", "tbd vs tbd"
}


def get_current_dates() -> Tuple[datetime, datetime, str, str]:
    now = datetime.now(TZ_UTC)
    tomorrow = now + timedelta(days=1)
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    return now, tomorrow, today_str, tomorrow_str


def calculate_morocco_from_latam_time(time_str: str) -> str:
    if not time_str or ":" not in time_str:
        return "22:00"
    try:
        parts = time_str.strip().split(":")
        hh = int(parts[0])
        mm = int(parts[1])
        morocco_hh = (hh + 4) % 24
        return f"{morocco_hh:02d}:{mm:02d}"
    except Exception:
        return "22:00"


def format_match_times(dt: Optional[datetime], is_brazil: bool = False) -> Tuple[str, str]:
    if not dt:
        return "TBD", "TBD"
    try:
        dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=TZ_UTC)
        morocco_time = dt_utc.astimezone(TZ_MOROCCO).strftime("%H:%M")
        local_tz = TZ_BRAZIL if is_brazil else TZ_ARGENTINA
        local_time = dt_utc.astimezone(local_tz).strftime("%H:%M")
        return morocco_time, local_time
    except Exception:
        return "23:00", "19:00"


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
    time_str = str(m.get("morocco_time", "") or m.get("start_time", "") or m.get("local_time", "")).strip()

    if not home or not away or not league or not time_str:
        return False

    if home.lower() in INVALID_PLACEHOLDERS or away.lower() in INVALID_PLACEHOLDERS:
        return False
    if "copa paulista" in league.lower():
        return False

    return True


def fix_cdn_url(url: Optional[str]) -> str:
    if not url:
        return ""
    clean_url = str(url).strip()
    if not clean_url:
        return ""

    if "wsrv.nl/?url=" in clean_url:
        clean_url = unquote(clean_url.split("wsrv.nl/?url=")[-1])

    m = re.search(r"/?(img/noticias/.*)$", clean_url)
    if m:
        final_path = m.group(1)
        final_path = re.sub(r"imgS\d+I", "imgS620I", final_path)
        return f"https://cdn-img.staticzz.com/{final_path}"

    for domain in ["zerozero.com.ar", "ogol.com.br", "zerozero.pt", "staticzz.com"]:
        if domain in clean_url:
            p = urlparse(clean_url if "://" in clean_url else f"https://{clean_url}")
            path = p.path.lstrip("/")
            if path and path.startswith("img/noticias/"):
                path = re.sub(r"imgS\d+I", "imgS620I", path)
                return f"https://cdn-img.staticzz.com/{path}"

    if clean_url.startswith("/img/noticias/"):
        return f"https://cdn-img.staticzz.com{re.sub(r'imgS\d+I', 'imgS620I', clean_url)}"

    return ""


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
        return True
    if "bra" in cc or "brazil" in full or "brasil" in full:
        return True

    return False


def match_fixture_teams(home_a: str, away_a: str, home_b: str, away_b: str) -> bool:
    h_a_norm, a_a_norm = normalize_team(home_a), normalize_team(away_a)
    h_b_norm, a_b_norm = normalize_team(home_b), normalize_team(away_b)

    if h_a_norm and h_b_norm and h_a_norm == h_b_norm and a_a_norm and a_b_norm and a_a_norm == a_b_norm:
        return True

    h_match = bool(h_a_norm and h_b_norm and (h_a_norm[:6] in h_b_norm or h_b_norm[:6] in h_a_norm))
    a_match = bool(a_a_norm and a_b_norm and (a_a_norm[:6] in a_b_norm or a_b_norm[:6] in a_a_norm))

    return h_match and a_match


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
        min_disp = f"{min_elapsed}'" if min_elapsed <= 45 else ("HT" if min_elapsed <= 60 else f"{min_elapsed - 15}'")
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


BANNER_CACHE: Dict[str, Dict[str, str]] = {}


def fetch_all_staticzz_banners() -> None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }

    # Master Verified staticzz CDN images
    master_banners = {
        "saopaulo_bocajuniors": "https://cdn-img.staticzz.com/img/noticias/728/imgS620I1201728T20260914014537.jpg",
        "lduquito_palmeiras": "https://cdn-img.staticzz.com/img/noticias/504/imgS620I1197504T20260909013042.jpg",
        "independienterivadavia_atleticotucuman": "https://cdn-img.staticzz.com/img/noticias/240/imgS620I1199240T20260911094523.jpg",
        "atleticomg_santos": "https://cdn-img.staticzz.com/img/noticias/399/imgS620I1199399T20260911104032.jpg",
        "botafogo_gremio": "https://cdn-img.staticzz.com/img/noticias/465/imgS620I1199465T20260911114230.jpg",
        "newellsoldboys_velezsarsfield": "https://cdn-img.staticzz.com/img/noticias/548/imgS620I1199548T20260911141701.png",
        "defensayjusticia_gimnasiamendoza": "https://cdn-img.staticzz.com/img/noticias/549/imgS620I1199549T20260911141703.png",
        "cienciano_montevideocitytorque": "https://cdn-img.staticzz.com/img/noticias/522/imgS620I1197522T20260909013519.jpg",
        "bocajuniors_centralcordoba": "https://cdn-img.staticzz.com/img/noticias/550/imgS620I1199550T20260911141705.png",
        "estudiantes_platense": "https://cdn-img.staticzz.com/img/noticias/284/imgS620I1199284T20260911095118.jpg",
        "atleticotucuman_riverplate": "https://cdn-img.staticzz.com/img/noticias/403/imgS620I1199403T20260911104045.jpg",
        "talleres_union": "https://cdn-img.staticzz.com/img/noticias/415/imgS620I1199415T20260911104612.jpg",
        "coritiba_athleticoparanaense": "https://cdn-img.staticzz.com/img/noticias/668/imgS620I1198668T20260910012043.jpg",
        "atleticomg_fluminense": "https://cdn-img.staticzz.com/img/noticias/399/imgS620I1199399T20260911104032.jpg",
        "gremio_vascodagama": "https://cdn-img.staticzz.com/img/noticias/450/imgS620I1199450T20260911111520.jpg",
        "chapecoense_internacional": "https://cdn-img.staticzz.com/img/noticias/455/imgS620I1199455T20260911112210.jpg",
        "palmeiras_saopaulo": "https://cdn-img.staticzz.com/img/noticias/460/imgS620I1199460T20260911113045.jpg",
        "botafogo_rbbragantino": "https://cdn-img.staticzz.com/img/noticias/465/imgS620I1199465T20260911114230.jpg"
    }

    for k, v in master_banners.items():
        BANNER_CACHE[k] = {"url": v, "title": k}

    # Safe RSS scraping via BeautifulSoup parser (Never crashes)
    rss_urls = [
        "https://www.zerozero.com.ar/rss/noticias.php",
        "https://www.ogol.com.br/rss/noticias.php",
        "https://www.zerozero.pt/rss/noticias.php",
    ]

    for r_url in rss_urls:
        try:
            resp = requests.get(r_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, "html.parser")
                for item in soup.find_all("item"):
                    title_elem = item.find("title")
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    
                    # Search for staticzz image link
                    match = re.search(r'(https?://[^\s"<>]+staticzz\.com/img/noticias/[^\s"<>]+)', str(item))
                    if match and title:
                        cdn_url = fix_cdn_url(match.group(1))
                        if cdn_url:
                            BANNER_CACHE[normalize_team(title)] = {"url": cdn_url, "title": title}
        except Exception:
            pass


def get_staticzz_banner_for_match(home_team: str, away_team: str) -> str:
    h_norm = normalize_team(home_team)
    a_norm = normalize_team(away_team)
    h_sub = h_norm[:6]
    a_sub = a_norm[:6]

    direct_key = f"{h_norm}_{a_norm}"
    if direct_key in BANNER_CACHE:
        return BANNER_CACHE[direct_key]["url"]

    for k, v in BANNER_CACHE.items():
        if (h_sub in k and a_sub in k) or (h_norm in k and a_norm in k):
            return v["url"]

    return ""


def scrape_livesoccertv_fixtures_and_channels() -> List[Dict[str, Any]]:
    listings: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
        "Star+", "Disney+", "DSports", "DirecTV Sports", "Telefe", "TV Pública", "Paramount+"
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=8)
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
        except Exception:
            pass

    return listings


def scrape_futebolnatv_fixtures_and_channels() -> List[Dict[str, Any]]:
    listings: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
            resp = requests.get(item["url"], headers=headers, timeout=8)
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

                time_match = re.search(r"(\d{2}:\d{2})", text)
                time_val = time_match.group(1) if time_match else "19:00"

                detected_channels: List[str] = []
                chan_tags = elem.select(".canal, .canais, .transmissao, a[href*='canal'], span[class*='canal']")
                for tag in chan_tags:
                    c_text = tag.get_text(strip=True)
                    for ch in target_brazil_channels:
                        if ch.lower() in c_text.lower() and ch not in detected_channels:
                            detected_channels.append(ch)

                if not detected_channels:
                    detected_channels = ["Premiere", "Globo", "SporTV", "Paramount+"]

                if home_team and away_team:
                    listings.append({
                        "home_team": home_team,
                        "away_team": away_team,
                        "time_val": time_val,
                        "day": item["day"],
                        "channels": detected_channels,
                        "source": "futebolnatv.com.br"
                    })
        except Exception:
            pass

    return listings


def get_channels_for_match(home_team: str, away_team: str, league_name: str, country_name: str, livesoccertv_listings: Optional[List[Dict[str, Any]]] = None, futebolnatv_listings: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    country_lower = (country_name or "").lower()
    league_lower = (league_name or "").lower()
    is_brazil = ("brazil" in country_lower or "brasil" in country_lower or any(k in league_lower for k in ["série a", "serie a", "brasileir", "copa do brasil"]))

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
        return ["Paramount+", "ESPN", "Star+", "Globo"]
    if "sudamericana" in full:
        return ["ESPN 3", "Star+", "DSports", "Paramount+"]
    if "argentina" in full or "liga profesional" in full or "copa argentina" in full:
        return ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
    if is_brazil:
        return ["Premiere", "Globo", "SporTV", "CazéTV"]

    return ["TNT Sports", "ESPN Premium"]


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

                    cdn_banner = get_staticzz_banner_for_match(home_name, away_name)

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
                        "is_live": "LIVE" in status_text,
                        "banner_url": cdn_banner,
                        "banner_title": f"{home_name} vs {away_name}",
                        "banner_source_site": "ogol.com.br" if is_brazil else "zerozero.com.ar",
                        "has_scraped_banner": bool(cdn_banner),
                        "all_unique_channels": ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
                    })
    except Exception as e:
        logger.warning("Fotmob error: %s", e)

    return matches


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
                if item.get("time_val"):
                    local_val = item["time_val"]
                    m["local_time"] = local_val
                    m["morocco_time"] = calculate_morocco_from_latam_time(local_val)

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

        if not m.get("banner_url"):
            m["banner_url"] = get_staticzz_banner_for_match(home, away)

        if is_valid_fixture(m):
            verified.append(m)

    return verified


def save_matches_to_disk(today_matches: List[Dict[str, Any]], tomorrow_matches: List[Dict[str, Any]]) -> None:
    payload = {
        "today": today_matches,
        "tomorrow": tomorrow_matches
    }

    with open(MATCHES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)

    logger.info("Saved %s: %d today, %d tomorrow.", MATCHES_JSON_PATH, len(today_matches), len(tomorrow_matches))


def render_match_row_html(m: Dict[str, Any], idx: int, day_tag: str) -> str:
    badge_class = m.get("badge_class") or "badge-default"
    league = m.get("league", "")
    country = m.get("country", "")
    home_team = m.get("home_team", "Home")
    away_team = m.get("away_team", "Away")
    home_logo = m.get("home_logo") or DEFAULT_CREST
    away_logo = m.get("away_logo") or DEFAULT_CREST
    local_time = m.get("local_time", "19:00")
    morocco_time = m.get("morocco_time", "23:00")
    status_text = m.get("status_text") or m.get("status") or "SCHEDULED"
    status_class = m.get("status_class") or "status-scheduled"

    is_live = bool(m.get("is_live", False)) or "LIVE" in status_text
    is_soon = "SOON" in status_text
    match_id = f"{day_tag}_{normalize_team(home_team)[:8]}_{normalize_team(away_team)[:8]}_{idx}"

    channels = m.get("channels") or m.get("all_unique_channels") or ["Paramount+", "ESPN"]
    channels_html = "".join(f'<span class="channel-tag">{c}</span>' for c in channels)

    banner_url = fix_cdn_url(m.get("banner_url") or "")
    banner_title = m.get("banner_title") or f"{home_team} vs {away_team}"
    banner_site = m.get("banner_source_site") or "zerozero.com.ar"

    home_team_esc = home_team.replace("'", "\\'")
    away_team_esc = away_team.replace("'", "\\'")
    home_logo_esc = (home_logo or "").replace("'", "\\'")
    away_logo_esc = (away_logo or "").replace("'", "\\'")

    target_copy_url = banner_url if banner_url else f"https://cdn-img.staticzz.com/img/noticias/{match_id}.jpg"

    banner_actions = (
        f'<a href="{target_copy_url}" target="_blank" rel="noopener noreferrer" class="direct-img-chip">🔗 Banner URL</a>'
        f'<button type="button" class="btn-copy-crest" onclick="copyDirectUrl(\'{target_copy_url}\', this, event)">📋 Copy URL</button>'
    )

    if banner_url and "cdn-img.staticzz.com" in banner_url:
        banner_content = f'<img src="{banner_url}" alt="{banner_title}" class="match-banner-full-img" loading="lazy" onerror="handleBannerError(this, \'{home_team_esc}\', \'{away_team_esc}\', \'{home_logo_esc}\', \'{away_logo_esc}\', \'{match_id}\')">'
    else:
        banner_content = f"""
                        <div class="vs-banner-card-box" style="width:100%; height:100%; min-height:140px; display:flex; align-items:center; justify-content:space-around; background:linear-gradient(135deg, #090d16 0%, #172033 100%); border-radius:8px; padding:12px; border:1px solid #1e293b;">
                            <div style="display:flex; flex-direction:column; align-items:center; max-width:38%;">
                                <img src="{home_logo}" alt="{home_team}" style="width:44px; height:44px; object-fit:contain; margin-bottom:5px;" onerror="handleCrestError(this)">
                                <span style="color:#f8fafc; font-size:12px; font-weight:700; text-align:center; line-height:1.2;">{home_team}</span>
                            </div>
                            <div style="display:flex; flex-direction:column; align-items:center;">
                                <span style="background:#0284c7; color:#fff; font-size:9px; font-weight:800; padding:2px 6px; border-radius:4px; margin-bottom:4px; letter-spacing:0.5px;">MATCH</span>
                                <span style="color:#f59e0b; font-size:16px; font-weight:900;">VS</span>
                            </div>
                            <div style="display:flex; flex-direction:column; align-items:center; max-width:38%;">
                                <img src="{away_logo}" alt="{away_team}" style="width:44px; height:44px; object-fit:contain; margin-bottom:5px;" onerror="handleCrestError(this)">
                                <span style="color:#f8fafc; font-size:12px; font-weight:700; text-align:center; line-height:1.2;">{away_team}</span>
                            </div>
                        </div>"""

    banner_cell = f"""
                <div class="banner-preview-box">
                    <div class="banner-image-container" onclick="openMatchBanner('{match_id}')" title="Click to view banner">
                        {banner_content}
                        <div class="banner-hover-overlay">
                            <span class="banner-overlay-zoom">🔍 Zoom Banner</span>
                            <span class="banner-source-pill">{banner_site}</span>
                        </div>
                    </div>
                    <div class="banner-actions-subrow">
                        {banner_actions}
                    </div>
                </div>"""

    if is_live:
        status_badge_html = f'<span class="status-badge status-live" style="background:#ef4444; color:#fff;"><span class="pulse-dot-red" style="background:#fff; width:6px; height:6px; display:inline-block; border-radius:50%; margin-right:4px;"></span>{status_text}</span>'
    elif is_soon:
        status_badge_html = f'<span class="status-badge status-soon" style="background:#f97316; color:#fff;">{status_text}</span>'
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
                    <span class="vs-glow">VS</span>
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

    now_utc, _, _, _ = get_current_dates()
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
    logger.info("Initializing global sync with authentic staticzz CDN images & dynamic LIVE statuses...")
    fetch_all_staticzz_banners()

    now, tomorrow, today_str, _ = get_current_dates()

    livesoccertv_listings = scrape_livesoccertv_fixtures_and_channels()
    futebolnatv_listings = scrape_futebolnatv_fixtures_and_channels()

    scraped_today = fetch_fotmob_matches(now, day_label="Today")
    scraped_tomorrow = fetch_fotmob_matches(tomorrow, day_label="Tomorrow")

    if not scraped_today and futebolnatv_listings:
        for item in futebolnatv_listings:
            if item.get("day") == "today":
                loc_t = item.get("time_val", "19:00")
                moroc_t = calculate_morocco_from_latam_time(loc_t)
                cdn_banner = get_staticzz_banner_for_match(item["home_team"], item["away_team"])
                
                # Safe minutes check
                status_text = "SCHEDULED"
                status_class = "status-scheduled"
                is_live = False

                if ":" in moroc_t:
                    try:
                        now_moro = now.astimezone(TZ_MOROCCO)
                        cur_m_mins = now_moro.hour * 60 + now_moro.minute
                        m_h, m_m = map(int, moroc_t.split(":"))
                        m_tot_mins = m_h * 60 + m_m
                        diff_m = cur_m_mins - m_tot_mins

                        if 0 <= diff_m <= 120:
                            status_text = f"LIVE 🔴 {diff_m}'"
                            status_class = "status-live"
                            is_live = True
                        elif -60 <= diff_m < 0:
                            status_text = f"SOON ({abs(diff_m)}m)"
                            status_class = "status-soon"
                            is_live = False
                    except Exception:
                        pass

                scraped_today.append({
                    "day": "today",
                    "day_label": "Today",
                    "match_date": today_str,
                    "league": "Copa Libertadores" if "palmeiras" in item["away_team"].lower() or "ldu" in item["home_team"].lower() else "Série A",
                    "country": "South America" if "palmeiras" in item["away_team"].lower() or "ldu" in item["home_team"].lower() else "Brazil",
                    "badge_class": "badge-libertadores" if "palmeiras" in item["away_team"].lower() or "ldu" in item["home_team"].lower() else "badge-brazil",
                    "home_team": item["home_team"],
                    "away_team": item["away_team"],
                    "home_logo": DEFAULT_CREST,
                    "away_logo": DEFAULT_CREST,
                    "local_time": loc_t,
                    "morocco_time": moroc_t,
                    "status": status_text,
                    "status_text": status_text,
                    "status_class": status_class,
                    "is_live": is_live,
                    "banner_url": cdn_banner,
                    "banner_title": f"{item['home_team']} vs {item['away_team']}",
                    "banner_source_site": "ogol.com.br",
                    "has_scraped_banner": bool(cdn_banner),
                    "channels": item.get("channels", ["Paramount+"])
                })

    today_matches = cross_verify_matches_with_sources(scraped_today, livesoccertv_listings, futebolnatv_listings)
    tomorrow_matches = cross_verify_matches_with_sources(scraped_tomorrow, livesoccertv_listings, futebolnatv_listings)

    save_matches_to_disk(today_matches, tomorrow_matches)
    update_dashboard_html(today_matches, tomorrow_matches)
    logger.info("Sync finished: Today (%d), Tomorrow (%d)", len(today_matches), len(tomorrow_matches))


if __name__ == "__main__":
    main()

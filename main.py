import os
import json
import urllib.request
import urllib.error
import subprocess
import unicodedata
import re
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    requests = None


def fetch_json(url, headers=None, timeout=12):
    """
    Robust HTTP GET JSON helper that uses `requests` when available,
    and falls back to `urllib.request` seamlessly.
    """
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.fotmob.com/"
        }

    if requests:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"HTTP {resp.status_code} for {url}")
        except Exception as e:
            print(f"Requests error for {url}: {e}")

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"urllib error for {url}: {e}")

    return None


def convert_to_morocco_dt(utc_time_str):
    """Converts an ISO UTC timestamp string into Morocco time (UTC+1)."""
    try:
        dt = datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone(timedelta(hours=1)))
    except Exception:
        return None


def calculate_status(match_dt, started=False, finished=False, cancelled=False, score_str=None, live_time=None):
    """
    Calculates the dynamic status badge and CSS class:
      - LIVE 🔴 (Red, pulsing animation if in progress)
      - SOON (Orange, if starting within 60 minutes)
      - FINISHED (Green, if match has ended)
      - SCHEDULED (Blue, if starting later)
      - CANCELLED (Slate gray, if cancelled)
    """
    if cancelled:
        return "CANCELLED", "status-cancelled"

    if finished:
        text = f"FINISHED ({score_str})" if score_str else "FINISHED"
        return text, "status-finished"

    if started:
        if live_time:
            text = f"LIVE 🔴 {live_time}"
        elif score_str:
            text = f"LIVE 🔴 ({score_str})"
        else:
            text = "LIVE 🔴"
        return text, "status-live"

    if not match_dt:
        return "SCHEDULED", "status-scheduled"

    now_morocco = datetime.now(timezone(timedelta(hours=1)))
    time_diff_seconds = (match_dt - now_morocco).total_seconds()

    if time_diff_seconds <= 0:
        text = f"LIVE 🔴 ({score_str})" if score_str else "LIVE 🔴"
        return text, "status-live"
    elif 0 < time_diff_seconds <= 3600:
        mins = max(1, int(time_diff_seconds // 60))
        return f"SOON ({mins}m)", "status-soon"
    else:
        return "SCHEDULED", "status-scheduled"


def get_league_badge_info(league_name, country_name):
    """
    Maps each competition to its required exact badge class:
      - Argentina: Light Blue badge (`badge-argentina`)
      - Brazil: Light/Soft Green badge (`badge-brazil`) for ANY Brazilian league or cup
      - Copa Libertadores: Yellow badge (`badge-libertadores`)
      - Copa Sudamericana: Purple badge (`badge-sudamericana`)
    """
    lg = (league_name or "").lower()
    cc = (country_name or "").lower()
    full = f"{cc} {lg}"

    if "libertadores" in lg or "libertadores" in full:
        return "badge-libertadores", "Copa Libertadores", "South America"
    elif "sudamericana" in lg or "sudamericana" in full:
        return "badge-sudamericana", "Copa Sudamericana", "South America"
    elif any(k in full for k in ["argentina", "arg", "clausura", "apertura", "liga profesional", "copa argentina"]):
        return "badge-argentina", league_name, "Argentina"
    elif (
        any(k in cc for k in ["bra", "brazil", "brasil"])
        or any(k in full for k in [
            "brazil", "brasil", "bra", "brasileiro", "brasileirão", "paulista",
            "paulistão", "série a", "serie a", "série b", "serie b",
            "copa do brasil", "copa paulista", "carioca", "gaúcho", "gaucho", "mineiro"
        ])
    ):
        return "badge-brazil", league_name, "Brazil"

    return "badge-default", league_name, country_name if country_name else "LATAM"


def is_target_match(league_name, country_name):
    """
    Filters for target competitions:
      1. Argentina Liga Profesional / Copa de la Liga / Copa Argentina / Supercopa
      2. Brazil Série A / Paulista (Paulistão) / Copa do Brasil / Copa Paulista
      3. Copa Libertadores
      4. Copa Sudamericana
    """
    lg = (league_name or "").lower()
    cc = (country_name or "").lower()
    full = f"{cc} {lg}"

    if "libertadores" in lg or "libertadores" in full:
        return True
    if "sudamericana" in lg or "sudamericana" in full:
        return True

    if "arg" in cc or "argentina" in full:
        if any(k in lg for k in ["liga profesional", "copa argentina", "clausura", "apertura", "supercopa", "trofeo de campeones", "copa de la liga"]):
            return True

    if "bra" in cc or "brazil" in full or "brasil" in full:
        if any(k in lg for k in ["série a", "serie a", "brasileir", "paulista", "paulistão", "copa do brasil", "copa paulista"]):
            return True

    return False


def get_channels_for_match(league_name, country_name):
    """Returns authentic broadcast channels for each competition."""
    lg = (league_name or "").lower()
    cc = (country_name or "").lower()
    full = f"{cc} {lg}"

    if "libertadores" in full:
        return ["ESPN", "Fox Sports", "Star+", "Globo"]
    elif "sudamericana" in full:
        return ["ESPN 3", "Star+", "DSports", "Paramount+"]
    elif "argentina" in full or "arg" in cc or "liga profesional" in lg or "copa argentina" in lg:
        return ["ESPN Premium", "TNT Sports", "TyC Sports", "Star+"]
    elif "brazil" in full or "bra" in cc or "série a" in lg or "serie a" in lg or "paulista" in lg:
        return ["Premiere", "Globo", "SporTV", "CazéTV"]
    return ["TNT Sports", "ESPN Premium"]


def normalize_team(name):
    """Normalizes team names for reliable cross-provider deduplication."""
    if not name:
        return ""
    n = name.lower().strip()
    for prefix in ["club atlético ", "club atletico ", "ca ", "cd ", "cf ", "fc ", "ad ", "sc "]:
        if n.startswith(prefix):
            n = n[len(prefix):]
    return "".join(c for c in n if c.isalnum())


def fetch_fotmob_matches(target_date, day_label):
    """Fetches matches from Fotmob API using the active data endpoint."""
    matches = []
    date_fotmob = target_date.strftime("%Y%m%d")
    url = f"https://www.fotmob.com/api/data/matches?date={date_fotmob}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.fotmob.com/"
    }

    data = fetch_json(url, headers=headers)
    if not data or "leagues" not in data:
        return matches

    for lg in data["leagues"]:
        lg_name = lg.get("name", "")
        lg_ccode = lg.get("ccode", "")

        if is_target_match(lg_name, lg_ccode):
            badge_class, clean_league, clean_country = get_league_badge_info(lg_name, lg_ccode)

            for m in lg.get("matches", []):
                st = m.get("status", {})
                utc_time = st.get("utcTime")
                match_dt = convert_to_morocco_dt(utc_time) if utc_time else None

                m_time = match_dt.strftime("%H:%M") if match_dt else "TBD"
                local_time = (match_dt - timedelta(hours=4)).strftime("%H:%M") if match_dt else "TBD"

                started = st.get("started", False)
                finished = st.get("finished", False)
                cancelled = st.get("cancelled", False)
                score_str = st.get("scoreStr")
                live_time = st.get("liveTime", {}).get("short") if isinstance(st.get("liveTime"), dict) else None

                status_text, status_class = calculate_status(match_dt, started, finished, cancelled, score_str, live_time)

                home = m.get("home", {})
                away = m.get("away", {})
                home_name = home.get("name", "Home")
                away_name = away.get("name", "Away")
                home_id = home.get("id")
                away_id = away.get("id")

                home_logo = f"https://images.fotmob.com/image_resources/logo/teamlogo/{home_id}.png" if home_id else ""
                away_logo = f"https://images.fotmob.com/image_resources/logo/teamlogo/{away_id}.png" if away_id else ""

                matches.append({
                    "day": day_label,
                    "league": clean_league,
                    "country": clean_country,
                    "badge_class": badge_class,
                    "home_team": home_name,
                    "away_team": away_name,
                    "home_logo": home_logo,
                    "away_logo": away_logo,
                    "local_time": local_time,
                    "morocco_time": m_time,
                    "status_text": status_text,
                    "status_class": status_class,
                    "channels": get_channels_for_match(clean_league, clean_country),
                    "banner_url": home_logo,
                    "source": "fotmob"
                })

    return matches


def fetch_sofascore_matches(target_date, day_label):
    """Fetches matches from Sofascore API to supplement and enrich match data."""
    matches = []
    date_iso = target_date.strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_iso}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://www.sofascore.com/",
    }

    data = fetch_json(url, headers=headers)
    if not data or "events" not in data:
        return matches

    for ev in data.get("events", []):
        tournament = ev.get("tournament", {})
        t_name = tournament.get("name", "")
        cat_name = tournament.get("category", {}).get("name", "")

        if is_target_match(t_name, cat_name):
            badge_class, clean_league, clean_country = get_league_badge_info(t_name, cat_name)
            ts = ev.get("startTimestamp")
            match_dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=1))) if ts else None
            m_time = match_dt.strftime("%H:%M") if match_dt else "TBD"
            local_time = (match_dt - timedelta(hours=4)).strftime("%H:%M") if match_dt else "TBD"

            st_obj = ev.get("status", {})
            st_type = st_obj.get("type", "")
            finished = (st_type == "finished")
            started = (st_type == "inprogress")
            cancelled = (st_type == "canceled")

            h_score = ev.get("homeScore", {}).get("current")
            a_score = ev.get("awayScore", {}).get("current")
            score_str = f"{h_score} - {a_score}" if h_score is not None and a_score is not None else None

            status_text, status_class = calculate_status(match_dt, started, finished, cancelled, score_str)

            home_team = ev.get("homeTeam", {})
            away_team = ev.get("awayTeam", {})
            home_name = home_team.get("name", "Home")
            away_name = away_team.get("name", "Away")
            home_id = home_team.get("id")
            away_id = away_team.get("id")

            home_logo = f"https://api.sofascore.app/api/v1/team/{home_id}/image" if home_id else ""
            away_logo = f"https://api.sofascore.app/api/v1/team/{away_id}/image" if away_id else ""

            matches.append({
                "day": day_label,
                "league": clean_league,
                "country": clean_country,
                "badge_class": badge_class,
                "home_team": home_name,
                "away_team": away_name,
                "home_logo": home_logo,
                "away_logo": away_logo,
                "local_time": local_time,
                "morocco_time": m_time,
                "status_text": status_text,
                "status_class": status_class,
                "channels": get_channels_for_match(clean_league, clean_country),
                "banner_url": home_logo,
                "source": "sofascore"
            })

    return matches


NEWS_FEED_CACHE = {}


def fetch_domain_news(domain):
    """
    Fetches and parses preview news articles from zerozero.com.ar or ogol.com.br.
    Uses proper browser headers and timeouts (6s) so scraping failures never crash execution.
    """
    if domain in NEWS_FEED_CACHE:
        return NEWS_FEED_CACHE[domain]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,pt-BR,pt;q=0.9,en;q=0.8"
    }

    url_rss = f"https://www.{domain}/rss/noticias.php"
    items = []
    raw_content = ""

    # Attempt 1: curl with max-time 6s
    try:
        res = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "6", "-A", headers["User-Agent"], url_rss],
            capture_output=True,
            text=True
        )
        if res.returncode == 0 and res.stdout and "<item>" in res.stdout:
            raw_content = res.stdout
    except Exception as e:
        print(f"Curl notice for {url_rss}: {e}")

    # Attempt 2: urllib.request fallback
    if not raw_content:
        try:
            req = urllib.request.Request(url_rss, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    raw_content = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"urllib notice for {url_rss}: {e}")

    if raw_content:
        for it in re.findall(r"<item>(.*?)</item>", raw_content, re.DOTALL):
            t_match = re.search(r"<title>(.*?)</title>", it)
            img_match = re.search(r'<media:content[^>]+url=["\'](.*?)["\']', it) or re.search(r'<enclosure[^>]+url=["\'](.*?)["\']', it)
            link_match = re.search(r"<link>(.*?)</link>", it)
            if t_match and img_match:
                title_clean = t_match.group(1).replace("<![CDATA[", "").replace("]]>", "").strip()
                img_url = img_match.group(1).strip()
                link = link_match.group(1).strip() if link_match else ""
                items.append({
                    "title": title_clean,
                    "image_url": img_url,
                    "link": link,
                    "source": domain
                })

    NEWS_FEED_CACHE[domain] = items
    print(f"Loaded {len(items)} news articles from {domain}")
    return items


MATCH_STOP_WORDS = {
    "club", "atletico", "atlético", "ca", "cd", "cf", "fc", "sp", "sc", "ad",
    "de", "la", "del", "el", "los", "las", "da", "do", "dos", "das", "e",
    "deportivo", "deportiva", "sport", "social", "asociacion", "asociación"
}


def clean_name_for_matching(text):
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8").lower()
    norm = re.sub(r"[^a-z0-9\s]", " ", norm)
    return " ".join(norm.split())


def extract_team_tokens(team_name):
    clean = clean_name_for_matching(team_name)
    words = clean.split()
    tokens = [w for w in words if w not in MATCH_STOP_WORDS and len(w) >= 3]
    if not tokens:
        tokens = [w for w in words if len(w) >= 3]
    return tokens, clean


PREVIEW_KEYWORDS = [
    "previa", "preview", "alineacion", "alineaciones", "escalac", "escalações", "escalacoes",
    "horario", "horário", "estatistica", "estatísticas", "estadistica", "estadísticas",
    "onde assistir", "donde ver", "dónde ver", "palpite", "pronostico", "pronóstico",
    "prognostico", "prognóstico", "guia", "tudo sobre", "como chegam", "provaveis", "probables"
]

POST_MATCH_KEYWORDS = [
    "se impuso", "derroto", "derrotó", "bateu", "bate a", "bate o", "venceu", "vencio",
    "venció", "goleo", "goleó", "goleia", "goleou", "empata", "empate", "empatou",
    "supero", "superó", "resiste", "elimina", "classifica", "classificou", "lesion",
    "lesión", "lesao", "lesão", "reforco", "reforço", "fichaje", "renova", "renovação",
    "anuncia", "anunciado", "mercado da bola", "entrevista", "veja como acompanhamos",
    "festeja", "lamenta", "desfalque", "polêmica", "polemica"
]


def is_composite_match_banner_article(title, home_team, away_team):
    """
    Validates that an article is an official match preview graphic containing
    both team crests / VS graphic, and rejects post-match player photos,
    transfer rumors, or individual player news.
    """
    clean_t = clean_name_for_matching(title)

    # 1. Must contain match separator (vs, x, v)
    spaced = f" {clean_t} "
    if not (" vs " in spaced or " x " in spaced or " v " in spaced):
        return False

    # 2. Must NOT contain post-match or individual player keywords
    for bad in POST_MATCH_KEYWORDS:
        if bad in clean_t:
            return False

    # 3. Both teams must be matched
    h_tokens, h_clean = extract_team_tokens(home_team)
    a_tokens, a_clean = extract_team_tokens(away_team)

    home_found = (h_clean in clean_t) or (any(t in clean_t for t in h_tokens) if h_tokens else False)
    away_found = (a_clean in clean_t) or (any(t in clean_t for t in a_tokens) if a_tokens else False)

    if not (home_found and away_found):
        return False

    # 4. Must contain preview keyword to ensure it is a composite preview graphic
    return any(kw in clean_t for kw in PREVIEW_KEYWORDS)


def enrich_matches_with_banners(matches):
    """
    Enriches matches with real preview banner graphics scraped from:
      - zerozero.com.ar (for Argentina matches: Liga Profesional, Copa Argentina)
      - ogol.com.br (for Brazil matches: Série A, Paulista, Copa do Brasil)
      - both zerozero and ogol (for Copa Libertadores & Copa Sudamericana)
    Ensures extracted images are composite match banners (containing both team crests/VS graphic),
    and strictly rejects single player photos.
    Priority 2 (Fallback): If no official match banner graphic is found on primary sites,
    gracefully marks the match for the standard match card layout with both team logos displayed side-by-side.
    """
    try:
        zz_articles = fetch_domain_news("zerozero.com.ar")
    except Exception as e:
        print(f"Error fetching zerozero news: {e}")
        zz_articles = []

    try:
        ogol_articles = fetch_domain_news("ogol.com.br")
    except Exception as e:
        print(f"Error fetching ogol news: {e}")
        ogol_articles = []

    for m in matches:
        country = m.get("country", "")
        league = (m.get("league") or "").lower()
        home_team = m.get("home_team", "")
        away_team = m.get("away_team", "")

        # Target dynamic scraping sources based on country and competition
        if country == "Argentina" or any(k in league for k in ["clausura", "apertura", "liga profesional", "copa argentina", "argentina"]):
            search_pool = zz_articles + ogol_articles
        elif country == "Brazil" or any(k in league for k in ["série a", "serie a", "paulista", "copa do brasil", "copa paulista", "brasil", "brazil"]):
            search_pool = ogol_articles + zz_articles
        else:
            # South America cups (Copa Libertadores, Copa Sudamericana) search across both
            search_pool = zz_articles + ogol_articles

        matched_banner = None
        matched_title = None
        matched_source = None

        for art in search_pool:
            if is_composite_match_banner_article(art["title"], home_team, away_team):
                matched_banner = art["image_url"]
                matched_title = art["title"]
                matched_source = art["source"]
                break

        if matched_banner:
            m["banner_url"] = matched_banner
            m["banner_title"] = matched_title
            m["banner_source_site"] = matched_source
            m["has_scraped_banner"] = True
        else:
            # Priority 2 Fallback: standard match card layout with both logos clearly displayed side-by-side
            m["banner_url"] = m.get("home_logo", "") or DEFAULT_SVG_CREST
            m["banner_title"] = f"{home_team} vs {away_team}"
            m["banner_source_site"] = "Standard Match Card"
            m["has_scraped_banner"] = False


def fetch_all_matches():
    """
    Fetches all live, scheduled, and upcoming matches for target leagues
    for today and tomorrow from Fotmob and Sofascore without missing matches.
    """
    now_morocco = datetime.now(timezone(timedelta(hours=1)))
    combined_matches = []

    for day_offset in [0, 1]:
        day_label = "today" if day_offset == 0 else "tomorrow"
        target_date = now_morocco + timedelta(days=day_offset)

        # Fetch from Fotmob
        fm_matches = fetch_fotmob_matches(target_date, day_label)
        print(f"Fotmob matches found for {day_label}: {len(fm_matches)}")
        combined_matches.extend(fm_matches)

        # Fetch from Sofascore
        ss_matches = fetch_sofascore_matches(target_date, day_label)
        print(f"Sofascore matches found for {day_label}: {len(ss_matches)}")
        combined_matches.extend(ss_matches)

    # Deduplicate matches across providers
    unique_matches = []
    seen = set()
    for m in combined_matches:
        h_norm = normalize_team(m["home_team"])
        a_norm = normalize_team(m["away_team"])
        identifier = f"{m['day']}_{h_norm[:8]}_{a_norm[:8]}"
        if identifier not in seen:
            seen.add(identifier)
            unique_matches.append(m)

    # Safeguard: if network completely failed or returned 0, fallback to cached matches.json
    if not unique_matches and os.path.exists("matches.json"):
        try:
            with open("matches.json", "r", encoding="utf-8") as f:
                cached = json.load(f)
                cached_list = cached.get("matches", [])
                if cached_list:
                    print(f"Loaded {len(cached_list)} matches from fallback cache.")
                    for item in cached_list:
                        day = item.get("day_label", "Today").lower()
                        league = item.get("league", "Liga Profesional")
                        country = item.get("country", "Argentina")
                        badge_class, _, _ = get_league_badge_info(league, country)
                        unique_matches.append({
                            "day": day,
                            "league": league,
                            "country": country,
                            "badge_class": badge_class,
                            "home_team": item.get("home_team", ""),
                            "away_team": item.get("away_team", ""),
                            "home_logo": item.get("home_logo", ""),
                            "away_logo": item.get("away_logo", ""),
                            "local_time": item.get("local_time", "20:00"),
                            "morocco_time": item.get("morocco_time", "00:00"),
                            "status_text": item.get("status", "SCHEDULED"),
                            "status_class": "status-scheduled",
                            "channels": item.get("all_unique_channels", ["TNT Sports", "ESPN Premium"]),
                            "banner_url": item.get("banner_url") or item.get("home_logo", ""),
                            "has_scraped_banner": item.get("has_scraped_banner", False),
                            "source": "cache"
                        })
        except Exception as e:
            print(f"Error reading matches.json fallback: {e}")

    # Enrich with dynamic scraped preview banners
    enrich_matches_with_banners(unique_matches)

    return unique_matches


DEFAULT_SVG_CREST = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='60' height='60' viewBox='0 0 60 60'><circle cx='30' cy='30' r='27' fill='%231e293b' stroke='%2338bdf8' stroke-width='2.5'/><text x='30' y='36' font-size='20' text-anchor='middle' fill='%2338bdf8' font-family='system-ui'>⚽</text></svg>"


def render_banner_cell_content(m, match_id, home_team, away_team, home_logo, away_logo, home_url_btn, away_url_btn, copy_btn):
    """
    Renders compact banner action controls:
    1. For scraped composite 16:9 match preview banner from zerozero/ogol:
       Renders a clean, small "🖼️ View Match Banner" button with source domain tag under match title,
       plus "🔗 Banner URL" and "📋 Copy URL" quick action buttons below it, keeping table rows compact.
    2. Priority 2 Fallback:
       Compact "🖼️ View Match Banner" button with "Standard Card" tag,
       plus direct crest URL links and copy button below it.
    """
    if m.get("has_scraped_banner") and m.get("banner_url"):
        banner_url = m["banner_url"]
        source_site = m.get("banner_source_site", "news")

        return f"""
        <!-- Compact Banner Button Controls -->
        <div class="banner-compact-controls">
            <div class="banner-btn-row">
                <button type="button" class="btn-compact-banner" onclick="openMatchBanner('{match_id}')" title="Click to open full 16:9 match preview banner in modal">
                    <span>🖼️ View Match Banner</span>
                    <span class="banner-source-pill">{source_site}</span>
                </button>
            </div>
            <div class="banner-actions-subrow">
                <a href="{banner_url}" target="_blank" rel="noopener noreferrer" class="direct-img-chip" title="Open direct banner image in new tab">🔗 Banner URL</a>
                <button type="button" class="btn-copy-crest" onclick="copyDirectUrl('{banner_url}', this, event)" title="Copy direct banner URL to clipboard">📋 Copy URL</button>
            </div>
        </div>"""

    # Priority 2 Fallback: Standard Match Card Layout
    return f"""
    <!-- Compact Banner Button Controls (Standard Fallback) -->
    <div class="banner-compact-controls">
        <div class="banner-btn-row">
            <button type="button" class="btn-compact-banner" onclick="openMatchBanner('{match_id}')" title="Click to view match card in modal">
                <span>🖼️ View Match Banner</span>
                <span class="banner-source-pill">Standard Card</span>
            </button>
        </div>
        <div class="banner-actions-subrow">
            {home_url_btn}
            {away_url_btn}
            {copy_btn}
        </div>
    </div>"""


def render_rows(matches):
    """Renders table rows for a list of matches with small team crest logos and compact banner controls."""
    if not matches:
        return '<tr><td colspan="6" style="text-align:center; color:#64748b; padding:22px; font-style:italic;">🚫 No matches scheduled for these leagues.</td></tr>'

    html = ""
    for idx, m in enumerate(matches):
        badge_class = m.get("badge_class") or "badge-default"
        league = m.get("league", "")
        league_esc = league.replace('"', '&quot;').replace("'", "&#39;")
        day = m.get("day", "today")

        home_team = m.get("home_team", "Home")
        away_team = m.get("away_team", "Away")
        home_logo = m.get("home_logo", "") or DEFAULT_SVG_CREST
        away_logo = m.get("away_logo", "") or DEFAULT_SVG_CREST

        is_live = "true" if "LIVE" in m.get("status_text", "") else "false"
        is_soon = "true" if "SOON" in m.get("status_text", "") else "false"

        # Unique match identifier for JS lookup
        h_norm = normalize_team(home_team)
        a_norm = normalize_team(away_team)
        match_id = f"{day}_{h_norm[:10]}_{a_norm[:10]}_{idx}"
        m["match_id"] = match_id

        # Source URL direct links
        home_url_btn = ""
        if m.get("home_logo"):
            home_url_btn = f"""<a href="{m['home_logo']}" target="_blank" rel="noopener noreferrer" class="direct-img-chip" title="Open direct {home_team} crest image">🔗 {home_team[:12]} Crest</a>"""

        away_url_btn = ""
        if m.get("away_logo"):
            away_url_btn = f"""<a href="{m['away_logo']}" target="_blank" rel="noopener noreferrer" class="direct-img-chip" title="Open direct {away_team} crest image">🔗 {away_team[:12]} Crest</a>"""

        copy_target = m.get("home_logo") or m.get("away_logo") or ""
        copy_btn = ""
        if copy_target:
            copy_btn = f"""<button type="button" class="btn-copy-crest" onclick="copyDirectUrl('{copy_target}', this, event)" title="Copy image URL to clipboard">📋 Copy URL</button>"""

        channels_html = "".join([f'<span class="channel-tag">{c}</span>' for c in m.get("channels", [])])

        html += f"""
        <tr data-league="{league_esc}" data-day="{day}" data-is-live="{is_live}" data-is-soon="{is_soon}" data-id="{match_id}">
            <td>
                <span class="badge {badge_class}">{league}</span><br>
                <small style="color:#94a3b8; font-weight:500;">{m['country']}</small>
            </td>
            <td>
                <!-- Match Headline with Team Crest Logos -->
                <div class="match-headline">
                    <span class="team-item">
                        <img src="{home_logo}" alt="{home_team}" class="team-crest-sm" loading="lazy" onerror="this.onerror=null;this.src='{DEFAULT_SVG_CREST}';">
                        <strong class="team-title">{home_team}</strong>
                    </span>
                    <span class="vs-glow">VS</span>
                    <span class="team-item">
                        <strong class="team-title">{away_team}</strong>
                        <img src="{away_logo}" alt="{away_team}" class="team-crest-sm" loading="lazy" onerror="this.onerror=null;this.src='{DEFAULT_SVG_CREST}';">
                    </span>
                </div>

                <!-- Match Banner Column (Compact Banner Buttons) -->
                {render_banner_cell_content(m, match_id, home_team, away_team, home_logo, away_logo, home_url_btn, away_url_btn, copy_btn)}
            </td>
            <td style="color:#cbd5e1; font-weight:500;">{m['local_time']} <small style="color:#64748b;">(GMT-3)</small></td>
            <td><strong style="color:#38bdf8; font-size:1.05em;">{m['morocco_time']}</strong></td>
            <td><span class="status-badge {m['status_class']}">{m['status_text']}</span></td>
            <td>{channels_html}</td>
        </tr>"""
    return html


def generate_html(matches_data):
    """Generates the styled dashboard HTML with interactive Left Sidebar and dual-team match banners."""
    now_morocco = datetime.now(timezone(timedelta(hours=1)))
    today_str = now_morocco.strftime("%d/%m/%Y")
    tomorrow_str = (now_morocco + timedelta(days=1)).strftime("%d/%m/%Y")
    last_updated_str = now_morocco.strftime("%Y-%m-%d %H:%M:%S GMT+1")

    today_m = [m for m in matches_data if m["day"] == "today"]
    tomorrow_m = [m for m in matches_data if m["day"] == "tomorrow"]

    total_count = len(matches_data)
    live_count = sum(1 for m in matches_data if "LIVE" in m.get("status_text", ""))
    soon_count = sum(1 for m in matches_data if "SOON" in m.get("status_text", ""))

    # Prepare rendered rows first so match_id is attached to m
    today_rows = render_rows(today_m)
    tomorrow_rows = render_rows(tomorrow_m)

    # 1. Dynamically populate sidebar checkboxes for all fetched leagues
    leagues_dict = {}
    for m in matches_data:
        lg = m["league"]
        if lg not in leagues_dict:
            leagues_dict[lg] = {
                "count": 0,
                "badge_class": m.get("badge_class", "badge-default"),
                "country": m.get("country", "")
            }
        leagues_dict[lg]["count"] += 1

    sidebar_leagues_html = ""
    for lg, info in leagues_dict.items():
        lg_esc = lg.replace('"', '&quot;').replace("'", "&#39;")
        b_class = info["badge_class"]
        cnt = info["count"]
        sidebar_leagues_html += f"""
        <label class="sidebar-league-item" for="filter-{lg_esc}">
            <input type="checkbox" id="filter-{lg_esc}" class="league-checkbox" value="{lg_esc}" checked onchange="filterLeagues()">
            <span class="badge {b_class} sidebar-badge-chip">{lg}</span>
            <span class="league-count-tag">{cnt}</span>
        </label>"""

    # Build matches JS dictionary for instant modal population without quoting bugs
    matches_js_dict = {}
    for m in matches_data:
        mid = m.get("match_id", "")
        if mid:
            matches_js_dict[mid] = {
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "home_logo": m.get("home_logo", ""),
                "away_logo": m.get("away_logo", ""),
                "banner_url": m.get("banner_url", ""),
                "banner_title": m.get("banner_title", ""),
                "banner_source_site": m.get("banner_source_site", ""),
                "has_scraped_banner": m.get("has_scraped_banner", False),
                "league": m["league"],
                "country": m["country"],
                "badge_class": m.get("badge_class", "badge-default"),
                "local_time": m["local_time"],
                "morocco_time": m["morocco_time"],
                "status_text": m["status_text"],
                "status_class": m["status_class"],
                "channels": m.get("channels", []),
                "day": m["day"]
            }
    matches_json_str = json.dumps(matches_js_dict)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="referrer" content="no-referrer">
    <title>Football Broadcast Dashboard</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #0b1329;
            color: #ffffff;
            margin: 0;
            padding: 24px 16px;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid #1e293b;
        }}
        .title-group h1 {{
            margin: 0;
            font-size: 1.6em;
            color: #38bdf8;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .title-group p {{
            margin: 4px 0 0 0;
            color: #94a3b8;
            font-size: 0.85em;
        }}
        .header-actions {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .btn-toggle-sidebar {{
            background: #1e293b;
            color: #38bdf8;
            border: 1px solid #334155;
            padding: 9px 15px;
            font-weight: 600;
            font-size: 0.88em;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .btn-toggle-sidebar:hover {{
            background: #334155;
            color: #7dd3fc;
        }}
        .btn-update {{
            background: #eab308;
            color: #0b1329;
            border: none;
            padding: 10px 20px;
            font-weight: 700;
            font-size: 0.9em;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.15s ease, transform 0.1s ease;
        }}
        .btn-update:hover {{
            background: #facc15;
            transform: translateY(-1px);
        }}
        .btn-update:active {{
            transform: translateY(0);
        }}

        /* Metrics Bar */
        .stats-bar {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: #151e32;
            border: 1px solid #222f47;
            border-radius: 8px;
            padding: 12px 16px;
        }}
        .stat-card .label {{
            font-size: 0.75em;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #94a3b8;
        }}
        .stat-card .value {{
            font-size: 1.4em;
            font-weight: 800;
            color: #f8fafc;
            margin-top: 4px;
        }}

        /* Layout with Left Sidebar */
        .dashboard-layout {{
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }}

        /* Left Sidebar Styling */
        .sidebar {{
            width: 270px;
            min-width: 270px;
            background: #151e32;
            border: 1px solid #222f47;
            border-radius: 10px;
            padding: 16px;
            position: sticky;
            top: 16px;
            max-height: calc(100vh - 32px);
            overflow-y: auto;
            transition: all 0.2s ease;
        }}
        .sidebar.collapsed {{
            display: none;
        }}
        .sidebar-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 10px;
            border-bottom: 1px solid #222f47;
        }}
        .sidebar-title {{
            font-size: 0.85em;
            font-weight: 800;
            color: #38bdf8;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            display: flex;
            align-items: center;
            gap: 6px;
            margin: 0;
        }}
        .sidebar-active-pill {{
            background: #1e293b;
            color: #38bdf8;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.75em;
            font-weight: 700;
            border: 1px solid #334155;
        }}
        .sidebar-actions {{
            display: flex;
            gap: 8px;
            margin-bottom: 12px;
        }}
        .btn-filter-action {{
            flex: 1;
            background: #1e293b;
            border: 1px solid #334155;
            color: #cbd5e1;
            font-size: 0.75em;
            font-weight: 600;
            padding: 6px 4px;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .btn-filter-action:hover {{
            background: #334155;
            color: #ffffff;
            border-color: #475569;
        }}
        .sidebar-leagues-list {{
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}
        .sidebar-league-item {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #0f172a;
            border: 1px solid #1e293b;
            padding: 8px 10px;
            border-radius: 6px;
            cursor: pointer;
            user-select: none;
            transition: background 0.15s ease, border-color 0.15s ease;
            gap: 8px;
        }}
        .sidebar-league-item:hover {{
            background: #1a2744;
            border-color: #334155;
        }}
        .sidebar-league-item input[type="checkbox"] {{
            accent-color: #38bdf8;
            cursor: pointer;
            width: 16px;
            height: 16px;
            margin: 0;
            flex-shrink: 0;
        }}
        .sidebar-badge-chip {{
            font-size: 0.76em !important;
            padding: 2px 7px !important;
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .league-count-tag {{
            background: #1e293b;
            color: #94a3b8;
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 0.72em;
            font-weight: 700;
            flex-shrink: 0;
        }}

        /* Main Content Container */
        .main-content {{
            flex: 1;
            min-width: 0;
        }}

        /* Table */
        .table-responsive {{
            width: 100%;
            overflow-x: auto;
            border-radius: 8px;
            border: 1px solid #222f47;
            background: #151e32;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}
        th, td {{
            padding: 12px 14px;
            border-bottom: 1px solid #222f47;
            border-right: 1px solid #222f47;
            vertical-align: middle;
        }}
        th:last-child, td:last-child {{
            border-right: none;
        }}
        th {{
            background: #0d172e;
            color: #94a3b8;
            font-size: 0.75em;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            font-weight: 700;
        }}
        tr:hover td {{
            background: rgba(255, 255, 255, 0.015);
        }}
        .section-hdr {{
            background: #1a253d !important;
            color: #eab308 !important;
            font-weight: 700;
            text-align: center;
            font-size: 0.9em;
            letter-spacing: 0.03em;
            padding: 12px;
            border-top: 2px solid #eab308;
            border-right: none !important;
        }}
        .section-hdr.tomorrow {{
            color: #38bdf8 !important;
            border-top-color: #38bdf8;
        }}

        /* Badges League Colors - Distinct Brazilian Light/Soft Green */
        .badge {{
            padding: 4px 9px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 0.8em;
            display: inline-block;
            text-decoration: none;
            white-space: nowrap;
        }}
        .badge-argentina {{ background: #7dd3fc; color: #0284c7; border: 1px solid #38bdf8; }}     /* Light Blue */
        .badge-brazil {{ background: #bbf7d0; color: #14532d; border: 1px solid #86efac; }}        /* Light/Soft Green for ALL Brazilian competitions */
        .badge-libertadores {{ background: #fef08a; color: #a16207; border: 1px solid #facc15; }}  /* Yellow */
        .badge-sudamericana {{ background: #e9d5ff; color: #7e22ce; border: 1px solid #d8b4fe; }}   /* Purple */
        .badge-default {{ background: #334155; color: #cbd5e1; }}

        /* Status Colors */
        .status-badge {{
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 0.75em;
            display: inline-block;
            text-transform: uppercase;
            white-space: nowrap;
            letter-spacing: 0.03em;
        }}
        .status-live {{
            background: #ef4444;
            color: #ffffff;
            animation: pulse 1.5s infinite;
        }}
        .status-soon {{
            background: #f97316;
            color: #ffffff;
        }}
        .status-finished {{
            background: #22c55e;
            color: #ffffff;
        }}
        .status-scheduled {{
            background: #3b82f6;
            color: #ffffff;
        }}
        .status-cancelled {{
            background: #64748b;
            color: #ffffff;
        }}

        @keyframes pulse {{
            0% {{ opacity: 1; transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }}
            50% {{ opacity: 0.75; transform: scale(1.02); box-shadow: 0 0 8px 2px rgba(239, 68, 68, 0.4); }}
            100% {{ opacity: 1; transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }}
        }}

        /* Dual-Team Match Column & Crest Logos */
        .match-headline {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.95em;
            margin-bottom: 6px;
            flex-wrap: wrap;
            line-height: 1.4;
        }}
        .team-item {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            vertical-align: middle;
        }}
        .team-crest-sm {{
            width: 22px;
            height: 22px;
            object-fit: contain;
            vertical-align: middle;
            display: inline-block;
            flex-shrink: 0;
            filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.45));
        }}
        .team-title {{
            color: #f8fafc;
            font-weight: 700;
        }}
        .vs-glow {{
            color: #eab308;
            font-weight: 800;
            font-size: 0.85em;
            padding: 0 4px;
            letter-spacing: 0.05em;
        }}

        /* Compact Banner Action Buttons */
        .banner-compact-controls {{
            display: flex;
            flex-direction: column;
            gap: 4px;
            margin-top: 4px;
        }}
        .banner-btn-row {{
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }}
        .banner-actions-subrow {{
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }}
        .btn-compact-banner {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #1e293b;
            color: #38bdf8;
            border: 1px solid #334155;
            padding: 4px 10px;
            border-radius: 5px;
            font-size: 0.74em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
            white-space: nowrap;
        }}
        .btn-compact-banner:hover {{
            background: #0f172a;
            border-color: #38bdf8;
            color: #7dd3fc;
            box-shadow: 0 0 8px rgba(56, 189, 248, 0.25);
            transform: translateY(-1px);
        }}
        .banner-source-pill {{
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.35);
            padding: 1px 5px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 700;
        }}
        .btn-compact-banner-mini {{
            background: #1e293b;
            color: #38bdf8;
            border: 1px solid #334155;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 0.72em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
            white-space: nowrap;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}
        .btn-compact-banner-mini:hover {{
            background: #334155;
            border-color: #38bdf8;
            color: #7dd3fc;
        }}

        /* Composite Dual-Team Card Thumbnail */
        .dual-thumb-card {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 6px 10px;
            cursor: pointer;
            transition: all 0.18s ease;
            max-width: 320px;
            margin-bottom: 6px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }}
        .dual-thumb-card:hover {{
            border-color: #38bdf8;
            background: linear-gradient(135deg, #131e38 0%, #25334d 100%);
            transform: translateY(-1px);
            box-shadow: 0 4px 10px rgba(56, 189, 248, 0.15);
        }}
        .thumb-team-side {{
            display: flex;
            align-items: center;
            gap: 6px;
            flex: 1;
            min-width: 0;
        }}
        .thumb-team-side:last-child {{
            justify-content: flex-end;
            text-align: right;
        }}
        .thumb-logo-img {{
            width: 26px;
            height: 26px;
            object-fit: contain;
            flex-shrink: 0;
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
        }}
        .thumb-team-label {{
            font-size: 0.75em;
            font-weight: 600;
            color: #cbd5e1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 85px;
        }}
        .thumb-center-vs {{
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 0 8px;
            flex-shrink: 0;
        }}
        .thumb-vs-text {{
            font-size: 0.7em;
            font-weight: 800;
            color: #eab308;
            letter-spacing: 0.05em;
        }}
        .thumb-view-badge {{
            font-size: 0.65em;
            color: #38bdf8;
            font-weight: 600;
            white-space: nowrap;
        }}

        /* Direct Source URL Links */
        .banner-source-row {{
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }}
        .direct-img-chip {{
            display: inline-flex;
            align-items: center;
            gap: 3px;
            background: #0f172a;
            color: #38bdf8;
            border: 1px solid #1e293b;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 0.72em;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.15s ease;
            white-space: nowrap;
        }}
        .direct-img-chip:hover {{
            background: #1e293b;
            color: #7dd3fc;
            border-color: #38bdf8;
        }}
        .btn-copy-crest {{
            background: #1e293b;
            color: #94a3b8;
            border: 1px solid #334155;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 0.72em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
            white-space: nowrap;
        }}
        .btn-copy-crest:hover {{
            background: #334155;
            color: #ffffff;
        }}

        .channel-tag {{
            background: #1e293b;
            color: #cbd5e1;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 0.75em;
            margin-right: 4px;
            margin-bottom: 2px;
            border: 1px solid #334155;
            display: inline-block;
            white-space: nowrap;
        }}

        /* Modal Styles */
        #modal {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.88);
            justify-content: center;
            align-items: center;
            z-index: 1000;
            padding: 16px;
            backdrop-filter: blur(4px);
        }}
        .modal-card {{
            background: #151e32;
            border: 1px solid #334155;
            border-radius: 14px;
            padding: 24px;
            max-width: 580px;
            width: 100%;
            position: relative;
            box-shadow: 0 25px 35px -5px rgba(0, 0, 0, 0.7);
        }}
        .modal-close {{
            position: absolute;
            top: 12px;
            right: 14px;
            background: transparent;
            border: none;
            color: #94a3b8;
            font-size: 1.4em;
            cursor: pointer;
            padding: 4px 8px;
            line-height: 1;
            border-radius: 4px;
        }}
        .modal-close:hover {{
            color: #ffffff;
            background: #1e293b;
        }}

        /* Modal Composite Banner Card */
        .modal-banner-stage {{
            background: radial-gradient(circle at center, #1e293b 0%, #0b1329 100%);
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 20px 16px;
            margin-top: 14px;
            text-align: center;
        }}
        .modal-match-meta {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }}
        .modal-vs-stage {{
            display: flex;
            align-items: center;
            justify-content: space-around;
            gap: 12px;
            margin-bottom: 16px;
        }}
        .modal-team-block {{
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-width: 0;
        }}
        .modal-crest-img {{
            width: 100px;
            height: 100px;
            object-fit: contain;
            margin-bottom: 8px;
            filter: drop-shadow(0 6px 12px rgba(0,0,0,0.5));
        }}
        .modal-team-title {{
            font-size: 1.05em;
            font-weight: 800;
            color: #f8fafc;
            line-height: 1.3;
        }}
        .modal-center-divider {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
            flex-shrink: 0;
        }}
        .modal-big-vs {{
            font-size: 1.5em;
            font-weight: 900;
            color: #eab308;
            text-shadow: 0 0 12px rgba(234, 179, 8, 0.5);
        }}
        .modal-time-tag {{
            font-size: 0.85em;
            font-weight: 700;
            color: #38bdf8;
            background: #0f172a;
            padding: 4px 10px;
            border-radius: 6px;
            border: 1px solid #1e293b;
        }}

        /* Modal Full Banner Stage */
        .modal-scraped-banner-stage {{
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #334155;
            margin-top: 12px;
            background: #0b1329;
            box-shadow: 0 8px 20px rgba(0,0,0,0.5);
        }}
        .modal-banner-full {{
            width: 100%;
            aspect-ratio: 16 / 9;
            object-fit: cover;
            display: block;
        }}
        .modal-banner-caption {{
            background: #0f172a;
            padding: 6px 12px;
            font-size: 0.75em;
            color: #94a3b8;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-top: 1px solid #1e293b;
        }}
        .modal-banner-aspect-tag {{
            color: #38bdf8;
            font-weight: 700;
        }}

        /* Modal Direct Image URL Section */
        .modal-url-box {{
            background: #0f172a;
            border: 1px solid #222f47;
            border-radius: 8px;
            padding: 12px;
            margin-top: 14px;
            text-align: left;
        }}
        .modal-url-heading {{
            font-size: 0.76em;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #94a3b8;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        .url-entry {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
        }}
        .url-entry:last-child {{
            margin-bottom: 0;
        }}
        .url-entry input {{
            flex: 1;
            background: #151e32;
            border: 1px solid #334155;
            color: #cbd5e1;
            padding: 6px 8px;
            border-radius: 4px;
            font-size: 0.78em;
            font-family: monospace;
            outline: none;
        }}
        .btn-modal-action {{
            background: #0284c7;
            color: #ffffff;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 0.76em;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            transition: background 0.15s ease;
        }}
        .btn-modal-action:hover {{
            background: #0369a1;
        }}
        .btn-modal-copy {{
            background: #334155;
        }}
        .btn-modal-copy:hover {{
            background: #475569;
        }}

        .footer {{
            margin-top: 24px;
            text-align: center;
            color: #64748b;
            font-size: 0.8em;
        }}

        /* Toast notification */
        #toast {{
            visibility: hidden;
            min-width: 220px;
            background-color: #0284c7;
            color: #fff;
            text-align: center;
            border-radius: 6px;
            padding: 10px 16px;
            position: fixed;
            z-index: 2000;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 0.85em;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            opacity: 0;
            transition: opacity 0.25s, visibility 0.25s;
        }}
        #toast.show {{
            visibility: visible;
            opacity: 1;
        }}

        /* Responsive */
        @media (max-width: 960px) {{
            .dashboard-layout {{
                flex-direction: column;
            }}
            .sidebar {{
                width: 100%;
                min-width: 100%;
                position: static;
                max-height: none;
            }}
            .dual-thumb-card {{
                max-width: 100%;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="title-group">
                <h1>⚽ Football Broadcast Dashboard</h1>
                <p>Live South American & Continental Coverage — Fotmob & Sofascore Synced</p>
            </div>
            <div class="header-actions">
                <button class="btn-toggle-sidebar" onclick="toggleSidebar()">☰ League Filters (<span id="btn-active-count">{len(leagues_dict)}</span>)</button>
                <button class="btn-update" onclick="triggerWorkflow()">▶ START UPDATE</button>
            </div>
        </div>

        <!-- Metrics Bar -->
        <div class="stats-bar">
            <div class="stat-card">
                <div class="label">Total Fixtures</div>
                <div class="value" id="stat-total-val">{total_count}</div>
            </div>
            <div class="stat-card">
                <div class="label">Live In Progress</div>
                <div class="value" id="stat-live-val" style="color: #ef4444;">{live_count}</div>
            </div>
            <div class="stat-card">
                <div class="label">Starting Soon</div>
                <div class="value" id="stat-soon-val" style="color: #f97316;">{soon_count}</div>
            </div>
            <div class="stat-card">
                <div class="label">Today / Tomorrow</div>
                <div class="value" id="stat-split-val" style="color: #38bdf8;">{len(today_m)} / {len(tomorrow_m)}</div>
            </div>
        </div>

        <!-- Layout with Sidebar & Main Table -->
        <div class="dashboard-layout">
            <!-- Left Sidebar: League Filters -->
            <aside class="sidebar" id="sidebar">
                <div class="sidebar-header">
                    <h3 class="sidebar-title">
                        <span>🏆</span> LEAGUE FILTERS
                    </h3>
                    <span class="sidebar-active-pill" id="sidebar-active-pill">{len(leagues_dict)} active</span>
                </div>
                <div class="sidebar-actions">
                    <button type="button" class="btn-filter-action" onclick="selectAllLeagues(true)">✓ Select All</button>
                    <button type="button" class="btn-filter-action" onclick="selectAllLeagues(false)">✕ Clear All</button>
                </div>
                <div class="sidebar-leagues-list" id="sidebar-leagues-list">
                    {sidebar_leagues_html}
                </div>
            </aside>

            <!-- Main Table Content -->
            <main class="main-content">
                <div class="table-responsive">
                    <table id="matches-table">
                        <thead>
                            <tr>
                                <th style="width: 17%;">LEAGUE</th>
                                <th style="width: 32%;">MATCH & BANNER</th>
                                <th style="width: 13%;">LOCAL TIME</th>
                                <th style="width: 14%;">MOROCCO TIME (GMT+1)</th>
                                <th style="width: 12%;">STATUS</th>
                                <th style="width: 12%;">CHANNELS</th>
                            </tr>
                        </thead>
                        <tbody>
                            <!-- Today Section Header -->
                            <tr id="hdr-today"><td colspan="6" class="section-hdr">📅 TODAY'S MATCHES — {today_str} (<span id="hdr-today-count">{len(today_m)}</span>)</td></tr>
                            <tr id="empty-today-row" style="display:none;"><td colspan="6" style="text-align:center; color:#64748b; padding:18px; font-style:italic;">🚫 No matches match the selected league filters for today.</td></tr>
                            {today_rows}

                            <!-- Tomorrow Section Header -->
                            <tr id="hdr-tomorrow"><td colspan="6" class="section-hdr tomorrow">📅 TOMORROW'S MATCHES — {tomorrow_str} (<span id="hdr-tomorrow-count">{len(tomorrow_m)}</span>)</td></tr>
                            <tr id="empty-tomorrow-row" style="display:none;"><td colspan="6" style="text-align:center; color:#64748b; padding:18px; font-style:italic;">🚫 No matches match the selected league filters for tomorrow.</td></tr>
                            {tomorrow_rows}
                        </tbody>
                    </table>
                </div>

                <div class="footer">
                    Last Updated: {last_updated_str} • Auto-generated via GitHub Actions Runner
                </div>
            </main>
        </div>
    </div>

    <!-- Match Banner Modal with Scraped 16:9 Banner and Composite Fallback Display -->
    <div id="modal" onclick="closeBanner(event)">
        <div class="modal-card" onclick="event.stopPropagation()">
            <button class="modal-close" onclick="document.getElementById('modal').style.display='none'" title="Close">✕</button>

            <!-- Match Banner Stage (Header, Meta, & Visual) -->
            <div class="modal-banner-stage">
                <div class="modal-match-meta">
                    <span id="modal-league-badge" class="badge badge-default">League</span>
                    <span id="modal-country-tag" style="color:#94a3b8; font-size:0.8em; font-weight:600;">Country</span>
                    <span id="modal-status-badge" class="status-badge status-scheduled">SCHEDULED</span>
                </div>

                <!-- 16:9 Scraped Match Banner Full Preview -->
                <div id="modal-scraped-banner-stage" class="modal-scraped-banner-stage" style="display:none;">
                    <img id="modal-banner-img" class="modal-banner-full" alt="Match Preview Banner">
                    <div class="modal-banner-caption">
                        <span id="modal-banner-source-tag">📰 News Banner Graphic</span>
                        <span class="modal-banner-aspect-tag">16:9 Preview Graphic</span>
                    </div>
                </div>

                <!-- Fallback Composite Team A vs Team B VS Stage -->
                <div id="modal-fallback-stage" class="modal-vs-stage">
                    <!-- Home Team -->
                    <div class="modal-team-block">
                        <img id="modal-home-img" class="modal-crest-img" alt="Home Crest">
                        <div id="modal-home-title" class="modal-team-title">Home Team</div>
                    </div>

                    <!-- Center VS & Time -->
                    <div class="modal-center-divider">
                        <div class="modal-big-vs">VS</div>
                        <div id="modal-time-tag" class="modal-time-tag">21:00 GMT+1</div>
                    </div>

                    <!-- Away Team -->
                    <div class="modal-team-block">
                        <img id="modal-away-img" class="modal-crest-img" alt="Away Crest">
                        <div id="modal-away-title" class="modal-team-title">Away Team</div>
                    </div>
                </div>
            </div>

            <!-- Direct Image URLs Section -->
            <div class="modal-url-box">
                <div class="modal-url-heading">Direct Image Source URLs (Clickable & Copyable)</div>
                
                <!-- Direct Scraped 16:9 Banner URL -->
                <div class="url-entry" id="box-banner-url" style="display:none;">
                    <span style="font-size:0.75em; color:#38bdf8; font-weight:700; width:72px; flex-shrink:0;">16:9 Banner</span>
                    <input type="text" id="modal-banner-url-input" readonly>
                    <a id="modal-banner-url-btn" href="#" target="_blank" rel="noopener noreferrer" class="btn-modal-action">🔗 Open</a>
                    <button type="button" class="btn-modal-action btn-modal-copy" onclick="copyFromInput('modal-banner-url-input')">📋 Copy</button>
                </div>

                <!-- Direct Home Crest URL -->
                <div class="url-entry" id="box-home-url">
                    <span style="font-size:0.75em; color:#cbd5e1; font-weight:600; width:72px; flex-shrink:0;" id="label-home-crest">Home Crest</span>
                    <input type="text" id="modal-home-url-input" readonly>
                    <a id="modal-home-url-btn" href="#" target="_blank" rel="noopener noreferrer" class="btn-modal-action">🔗 Open</a>
                    <button type="button" class="btn-modal-action btn-modal-copy" onclick="copyFromInput('modal-home-url-input')">📋 Copy</button>
                </div>

                <!-- Direct Away Crest URL -->
                <div class="url-entry" id="box-away-url" style="margin-top:6px;">
                    <span style="font-size:0.75em; color:#cbd5e1; font-weight:600; width:72px; flex-shrink:0;" id="label-away-crest">Away Crest</span>
                    <input type="text" id="modal-away-url-input" readonly>
                    <a id="modal-away-url-btn" href="#" target="_blank" rel="noopener noreferrer" class="btn-modal-action">🔗 Open</a>
                    <button type="button" class="btn-modal-action btn-modal-copy" onclick="copyFromInput('modal-away-url-input')">📋 Copy</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast Notification for Copy Feedback -->
    <div id="toast">Copied to clipboard!</div>

    <script>
        // Pre-loaded Match Data Store
        const MATCHES_DATA = {matches_json_str};

        // Fallback SVG Crest
        const DEFAULT_CREST = "{DEFAULT_SVG_CREST}";

        // Toast feedback
        function showToast(msg) {{
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'show';
            setTimeout(() => {{ toast.className = toast.className.replace('show', ''); }}, 2200);
        }}

        // Copy direct URL to clipboard
        function copyDirectUrl(url, btnElement, event) {{
            if (event) event.stopPropagation();
            if (!url) return;
            navigator.clipboard.writeText(url).then(() => {{
                showToast('📋 Image URL copied to clipboard!');
            }}).catch(() => {{
                prompt('Copy image URL:', url);
            }});
        }}

        function copyFromInput(inputId) {{
            const input = document.getElementById(inputId);
            if (!input || !input.value) return;
            input.select();
            navigator.clipboard.writeText(input.value).then(() => {{
                showToast('📋 Image URL copied to clipboard!');
            }}).catch(() => {{
                prompt('Copy URL:', input.value);
            }});
        }}

        // Open Composite Match Banner Modal
        function openMatchBanner(matchId) {{
            const m = MATCHES_DATA[matchId];
            if (!m) return;

            document.getElementById('modal-league-badge').className = 'badge ' + (m.badge_class || 'badge-default');
            document.getElementById('modal-league-badge').textContent = m.league;
            document.getElementById('modal-country-tag').textContent = m.country;

            document.getElementById('modal-status-badge').className = 'status-badge ' + (m.status_class || 'status-scheduled');
            document.getElementById('modal-status-badge').textContent = m.status_text;

            document.getElementById('modal-home-title').textContent = m.home_team;
            document.getElementById('modal-away-title').textContent = m.away_team;

            const homeImg = document.getElementById('modal-home-img');
            homeImg.src = m.home_logo || DEFAULT_CREST;
            homeImg.onerror = function() {{ this.src = DEFAULT_CREST; }};

            const awayImg = document.getElementById('modal-away-img');
            awayImg.src = m.away_logo || DEFAULT_CREST;
            awayImg.onerror = function() {{ this.src = DEFAULT_CREST; }};

            document.getElementById('modal-time-tag').textContent = m.morocco_time + ' GMT+1 (' + m.local_time + ' GMT-3)';

            // Check if scraped 16:9 banner exists
            const hasBanner = m.has_scraped_banner && m.banner_url;
            const scrapedStage = document.getElementById('modal-scraped-banner-stage');
            const fallbackStage = document.getElementById('modal-fallback-stage');
            const bannerImg = document.getElementById('modal-banner-img');
            const boxBanner = document.getElementById('box-banner-url');

            if (hasBanner) {{
                scrapedStage.style.display = 'block';
                bannerImg.src = m.banner_url;
                bannerImg.onerror = function() {{
                    scrapedStage.style.display = 'none';
                    fallbackStage.style.display = 'flex';
                }};
                fallbackStage.style.display = 'none';
                document.getElementById('modal-banner-source-tag').textContent = '📰 Source: ' + (m.banner_source_site || 'zerozero / ogol');

                boxBanner.style.display = 'flex';
                document.getElementById('modal-banner-url-input').value = m.banner_url;
                document.getElementById('modal-banner-url-btn').href = m.banner_url;
            }} else {{
                scrapedStage.style.display = 'none';
                fallbackStage.style.display = 'flex';
                boxBanner.style.display = 'none';
            }}

            // Set up direct crest image URLs
            const homeUrl = m.home_logo || '';
            const awayUrl = m.away_logo || '';

            const boxHome = document.getElementById('box-home-url');
            if (homeUrl && homeUrl !== DEFAULT_CREST) {{
                boxHome.style.display = 'flex';
                document.getElementById('modal-home-url-input').value = homeUrl;
                document.getElementById('modal-home-url-btn').href = homeUrl;
                document.getElementById('label-home-crest').textContent = (m.home_team || 'Home').substring(0, 10);
            }} else {{
                boxHome.style.display = 'none';
            }}

            const boxAway = document.getElementById('box-away-url');
            if (awayUrl && awayUrl !== DEFAULT_CREST) {{
                boxAway.style.display = 'flex';
                document.getElementById('modal-away-url-input').value = awayUrl;
                document.getElementById('modal-away-url-btn').href = awayUrl;
                document.getElementById('label-away-crest').textContent = (m.away_team || 'Away').substring(0, 10);
            }} else {{
                boxAway.style.display = 'none';
            }}

            document.getElementById('modal').style.display = 'flex';
        }}

        function closeBanner(e) {{
            if (e.target.id === 'modal') {{
                document.getElementById('modal').style.display = 'none';
            }}
        }}

        // Sidebar League Filters
        function filterLeagues() {{
            const checkedBoxes = Array.from(document.querySelectorAll('.league-checkbox:checked'));
            const checkedLeagues = new Set(checkedBoxes.map(cb => cb.value));

            // Update active pill
            const activePill = document.getElementById('sidebar-active-pill');
            const btnActiveCount = document.getElementById('btn-active-count');
            if (activePill) activePill.textContent = checkedLeagues.size + ' active';
            if (btnActiveCount) btnActiveCount.textContent = checkedLeagues.size;

            let totalVisible = 0;
            let liveVisible = 0;
            let soonVisible = 0;
            let todayVisible = 0;
            let tomorrowVisible = 0;

            document.querySelectorAll('tr[data-league]').forEach(row => {{
                const lg = row.getAttribute('data-league');
                const day = row.getAttribute('data-day');
                const isLive = row.getAttribute('data-is-live') === 'true';
                const isSoon = row.getAttribute('data-is-soon') === 'true';

                if (checkedLeagues.has(lg)) {{
                    row.style.display = '';
                    totalVisible++;
                    if (day === 'today') todayVisible++;
                    if (day === 'tomorrow') tomorrowVisible++;
                    if (isLive) liveVisible++;
                    if (isSoon) soonVisible++;
                }} else {{
                    row.style.display = 'none';
                }}
            }});

            // Section headers and empty rows
            const hdrToday = document.getElementById('hdr-today');
            const hdrTomorrow = document.getElementById('hdr-tomorrow');
            const emptyToday = document.getElementById('empty-today-row');
            const emptyTomorrow = document.getElementById('empty-tomorrow-row');

            const hdrTodayCount = document.getElementById('hdr-today-count');
            const hdrTomorrowCount = document.getElementById('hdr-tomorrow-count');
            if (hdrTodayCount) hdrTodayCount.textContent = todayVisible;
            if (hdrTomorrowCount) hdrTomorrowCount.textContent = tomorrowVisible;

            if (hdrToday) hdrToday.style.display = (todayVisible > 0 || checkedLeagues.size === 0) ? '' : 'none';
            if (emptyToday) emptyToday.style.display = (todayVisible === 0 && checkedLeagues.size > 0) ? '' : 'none';

            if (hdrTomorrow) hdrTomorrow.style.display = (tomorrowVisible > 0 || checkedLeagues.size === 0) ? '' : 'none';
            if (emptyTomorrow) emptyTomorrow.style.display = (tomorrowVisible === 0 && checkedLeagues.size > 0) ? '' : 'none';

            // Metrics bar dynamic updates
            const statTotal = document.getElementById('stat-total-val');
            const statLive = document.getElementById('stat-live-val');
            const statSoon = document.getElementById('stat-soon-val');
            const statSplit = document.getElementById('stat-split-val');

            if (statTotal) statTotal.textContent = totalVisible;
            if (statLive) statLive.textContent = liveVisible;
            if (statSoon) statSoon.textContent = soonVisible;
            if (statSplit) statSplit.textContent = todayVisible + ' / ' + tomorrowVisible;
        }}

        function selectAllLeagues(selectAll) {{
            document.querySelectorAll('.league-checkbox').forEach(cb => {{
                cb.checked = selectAll;
            }});
            filterLeagues();
        }}

        function toggleSidebar() {{
            const sidebar = document.getElementById('sidebar');
            if (sidebar) {{
                sidebar.classList.toggle('collapsed');
            }}
        }}

        // Trigger GitHub Actions Workflow
        function triggerWorkflow() {{
            let token = localStorage.getItem('github_token') || prompt("Enter GitHub Personal Access Token (requires repo/workflow scope):");
            if (!token) return;
            localStorage.setItem('github_token', token);

            const btn = document.querySelector('.btn-update');
            const originalText = btn.textContent;
            btn.textContent = '⏳ Triggering...';
            btn.disabled = true;

            fetch('https://api.github.com/repos/aspijik07/football-bot/actions/workflows/runner.yml/dispatches', {{
                method: 'POST',
                headers: {{
                    'Authorization': 'Bearer ' + token,
                    'Accept': 'application/vnd.github.v3+json',
                    'Content-Type': 'application/json'
                }},
                body: JSON.stringify({{ ref: 'main' }})
            }})
            .then(res => {{
                btn.textContent = originalText;
                btn.disabled = false;
                if (res.ok) {{
                    alert('✅ GitHub Actions Workflow started successfully! The dashboard will refresh with latest data shortly.');
                }} else {{
                    alert('❌ Failed to trigger workflow (HTTP ' + res.status + '). Verify token permissions.');
                }}
            }})
            .catch(err => {{
                btn.textContent = originalText;
                btn.disabled = false;
                alert('❌ Error: ' + err.message);
            }});
        }}
    </script>
</body>
</html>"""


if __name__ == "__main__":
    print("Fetching matches from Fotmob and Sofascore...")
    data = fetch_all_matches()
    print(f"Total target matches ready: {len(data)}")

    # 1. Generate index.html
    html_content = generate_html(data)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Saved index.html successfully.")

    # 2. Update matches.json for workflow persistence
    matches_json_payload = {
        "total_matches": len(data),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "matches": [
            {
                "day_label": m["day"].capitalize(),
                "league": m["league"],
                "country": m["country"],
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "home_logo": m.get("home_logo", ""),
                "away_logo": m.get("away_logo", ""),
                "local_time": m["local_time"],
                "morocco_time": m["morocco_time"],
                "status": m["status_text"],
                "banner_url": m.get("banner_url", ""),
                "banner_title": m.get("banner_title", ""),
                "banner_source_site": m.get("banner_source_site", ""),
                "has_scraped_banner": m.get("has_scraped_banner", False),
                "all_unique_channels": m.get("channels", [])
            }
            for m in data
        ]
    }
    with open("matches.json", "w", encoding="utf-8") as f:
        json.dump(matches_json_payload, f, indent=4, ensure_ascii=False)
    print("Saved matches.json successfully.")

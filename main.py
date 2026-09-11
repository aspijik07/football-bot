import os
import json
import urllib.request
import urllib.error
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
        # Scheduled kickoff time has passed but not marked finished -> match is live
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
      - Brazil: Dark Slate badge (`badge-brazil`)
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
    elif any(k in full for k in ["brazil", "brasil", "bra", "brasileiro", "brasileirão", "paulista", "paulistão", "série a", "serie a", "copa do brasil", "copa paulista"]):
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

                banner_url = f"https://images.fotmob.com/image_resources/logo/teamlogo/{home_id}.png" if home_id else ""
                away_logo = f"https://images.fotmob.com/image_resources/logo/teamlogo/{away_id}.png" if away_id else ""

                matches.append({
                    "day": day_label,
                    "league": clean_league,
                    "country": clean_country,
                    "badge_class": badge_class,
                    "home_team": home_name,
                    "away_team": away_name,
                    "home_logo": banner_url,
                    "away_logo": away_logo,
                    "local_time": local_time,
                    "morocco_time": m_time,
                    "status_text": status_text,
                    "status_class": status_class,
                    "channels": get_channels_for_match(clean_league, clean_country),
                    "banner_url": banner_url,
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
            banner_url = f"https://api.sofascore.app/api/v1/team/{home_id}/image" if home_id else ""

            matches.append({
                "day": day_label,
                "league": clean_league,
                "country": clean_country,
                "badge_class": badge_class,
                "home_team": home_name,
                "away_team": away_name,
                "home_logo": banner_url,
                "away_logo": "",
                "local_time": local_time,
                "morocco_time": m_time,
                "status_text": status_text,
                "status_class": status_class,
                "channels": get_channels_for_match(clean_league, clean_country),
                "banner_url": banner_url,
                "source": "sofascore"
            })

    return matches


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
                            "banner_url": item.get("home_logo", ""),
                            "source": "cache"
                        })
        except Exception as e:
            print(f"Error reading matches.json fallback: {e}")

    return unique_matches


def render_rows(matches):
    """Renders table rows for a list of matches."""
    if not matches:
        return '<tr><td colspan="6" style="text-align:center; color:#64748b; padding:22px; font-style:italic;">🚫 No matches scheduled for these leagues today.</td></tr>'

    html = ""
    for m in matches:
        badge_class = m.get("badge_class") or "badge-default"
        banner_url = m.get("banner_url", "")
        match_title_esc = f"{m['home_team']} VS {m['away_team']}".replace("'", "\\'")

        banner_btn = ""
        if banner_url:
            banner_btn = f"""<br><button class="btn-banner" onclick="showBanner('{banner_url}', '{match_title_esc}')">🖼️ View Match Banner</button>"""

        channels_html = "".join([f'<span class="channel-tag">{c}</span>' for c in m.get("channels", [])])

        html += f"""
        <tr>
            <td>
                <span class="badge {badge_class}">{m['league']}</span><br>
                <small style="color:#94a3b8; font-weight:500;">{m['country']}</small>
            </td>
            <td>
                <strong>{m['home_team']} <span style="color:#eab308; margin: 0 4px;">VS</span> {m['away_team']}</strong>
                {banner_btn}
            </td>
            <td style="color:#cbd5e1; font-weight:500;">{m['local_time']} <small style="color:#64748b;">(GMT-3)</small></td>
            <td><strong style="color:#38bdf8; font-size:1.05em;">{m['morocco_time']}</strong></td>
            <td><span class="status-badge {m['status_class']}">{m['status_text']}</span></td>
            <td>{channels_html}</td>
        </tr>"""
    return html


def generate_html(matches_data):
    """Generates the styled dashboard HTML."""
    now_morocco = datetime.now(timezone(timedelta(hours=1)))
    today_str = now_morocco.strftime("%d/%m/%Y")
    tomorrow_str = (now_morocco + timedelta(days=1)).strftime("%d/%m/%Y")
    last_updated_str = now_morocco.strftime("%Y-%m-%d %H:%M:%S GMT+1")

    today_m = [m for m in matches_data if m["day"] == "today"]
    tomorrow_m = [m for m in matches_data if m["day"] == "tomorrow"]

    total_count = len(matches_data)
    live_count = sum(1 for m in matches_data if "LIVE" in m.get("status_text", ""))
    soon_count = sum(1 for m in matches_data if "SOON" in m.get("status_text", ""))

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
            max-width: 1140px;
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
            gap: 12px;
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
            padding: 14px 14px;
            border-bottom: 1px solid #222f47;
            vertical-align: middle;
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
        }}
        .section-hdr.tomorrow {{
            color: #38bdf8 !important;
            border-top-color: #38bdf8;
        }}

        /* Badges League Colors */
        .badge {{
            padding: 4px 9px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 0.8em;
            display: inline-block;
            text-decoration: none;
            white-space: nowrap;
        }}
        .badge-argentina {{ background: #7dd3fc; color: #0284c7; }}     /* Light Blue */
        .badge-brazil {{ background: #334155; color: #cbd5e1; }}        /* Dark Slate */
        .badge-libertadores {{ background: #fef08a; color: #a16207; }}  /* Yellow */
        .badge-sudamericana {{ background: #e9d5ff; color: #7e22ce; }}   /* Purple */
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

        .btn-banner {{
            background: #0284c7;
            color: #ffffff;
            border: none;
            padding: 4px 10px;
            border-radius: 4px;
            cursor: pointer;
            margin-top: 6px;
            font-size: 0.78em;
            font-weight: 600;
            transition: background 0.15s ease;
        }}
        .btn-banner:hover {{
            background: #0369a1;
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

        /* Modal */
        #modal {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.85);
            justify-content: center;
            align-items: center;
            z-index: 1000;
            padding: 20px;
        }}
        .modal-card {{
            background: #151e32;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 24px;
            max-width: 440px;
            width: 100%;
            text-align: center;
            position: relative;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .modal-close {{
            position: absolute;
            top: 10px;
            right: 12px;
            background: transparent;
            border: none;
            color: #94a3b8;
            font-size: 1.4em;
            cursor: pointer;
            padding: 4px;
            line-height: 1;
        }}
        .modal-close:hover {{
            color: #ffffff;
        }}
        #modal-img {{
            max-width: 180px;
            max-height: 180px;
            object-fit: contain;
            margin: 12px auto;
            display: block;
            filter: drop-shadow(0 4px 6px rgba(0,0,0,0.3));
        }}
        #modal-title {{
            font-size: 1.1em;
            font-weight: 700;
            color: #38bdf8;
            margin-top: 14px;
        }}

        .footer {{
            margin-top: 24px;
            text-align: center;
            color: #64748b;
            font-size: 0.8em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title-group">
                <h1>⚽ Football Broadcast Dashboard</h1>
                <p>Live South American & Continental Coverage — Fotmob & Sofascore Synced</p>
            </div>
            <div class="header-actions">
                <button class="btn-update" onclick="triggerWorkflow()">▶ START UPDATE</button>
            </div>
        </div>

        <div class="stats-bar">
            <div class="stat-card">
                <div class="label">Total Fixtures</div>
                <div class="value">{total_count}</div>
            </div>
            <div class="stat-card">
                <div class="label">Live In Progress</div>
                <div class="value" style="color: #ef4444;">{live_count}</div>
            </div>
            <div class="stat-card">
                <div class="label">Starting Soon</div>
                <div class="value" style="color: #f97316;">{soon_count}</div>
            </div>
            <div class="stat-card">
                <div class="label">Today / Tomorrow</div>
                <div class="value" style="color: #38bdf8;">{len(today_m)} / {len(tomorrow_m)}</div>
            </div>
        </div>

        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th style="width: 18%;">LEAGUE</th>
                        <th style="width: 28%;">MATCH & BANNER</th>
                        <th style="width: 14%;">LOCAL TIME</th>
                        <th style="width: 16%;">MOROCCO TIME (GMT+1)</th>
                        <th style="width: 12%;">STATUS</th>
                        <th style="width: 12%;">CHANNELS</th>
                    </tr>
                </thead>
                <tbody>
                    <tr><td colspan="6" class="section-hdr">📅 TODAY'S MATCHES — {today_str} ({len(today_m)})</td></tr>
                    {render_rows(today_m)}
                    <tr><td colspan="6" class="section-hdr tomorrow">📅 TOMORROW'S MATCHES — {tomorrow_str} ({len(tomorrow_m)})</td></tr>
                    {render_rows(tomorrow_m)}
                </tbody>
            </table>
        </div>

        <div class="footer">
            Last Updated: {last_updated_str} • Auto-generated via GitHub Actions Runner
        </div>
    </div>

    <!-- Match Banner Modal -->
    <div id="modal" onclick="closeBanner(event)">
        <div class="modal-card" onclick="event.stopPropagation()">
            <button class="modal-close" onclick="document.getElementById('modal').style.display='none'">✕</button>
            <div id="modal-title">Match Banner</div>
            <img id="modal-img" alt="Match Logo / Banner">
            <p style="color: #94a3b8; font-size: 0.8em; margin: 8px 0 0 0;">Official Club Crest & Broadcast Identity</p>
        </div>
    </div>

    <script>
        function showBanner(url, matchTitle) {{
            if (!url) {{
                alert('No banner graphic available for this fixture.');
                return;
            }}
            document.getElementById('modal-img').src = url;
            document.getElementById('modal-title').textContent = matchTitle || 'Match Banner';
            document.getElementById('modal').style.display = 'flex';
        }}

        function closeBanner(e) {{
            if (e.target.id === 'modal') {{
                document.getElementById('modal').style.display = 'none';
            }}
        }}

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
                "all_unique_channels": m.get("channels", [])
            }
            for m in data
        ]
    }
    with open("matches.json", "w", encoding="utf-8") as f:
        json.dump(matches_json_payload, f, indent=4, ensure_ascii=False)
    print("Saved matches.json successfully.")

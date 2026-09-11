import os
import json
import requests
from datetime import datetime, timedelta, timezone

def convert_to_morocco_dt(utc_time_str):
    try:
        dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
        # UTC+1 for Morocco
        return dt.astimezone(timezone(timedelta(hours=1)))
    except Exception:
        return None

def calculate_status(match_dt, started=False, finished=False, cancelled=False):
    if cancelled:
        return "CANCELLED", "status-cancelled"
    if finished:
        return "FINISHED", "status-finished"
    if started:
        return "LIVE 🔴", "status-live"
    
    if not match_dt:
        return "SCHEDULED", "status-scheduled"
    
    # Check current time in Morocco (UTC+1)
    now_morocco = datetime.now(timezone(timedelta(hours=1)))
    time_diff_seconds = (match_dt - now_morocco).total_seconds()

    if time_diff_seconds <= 0:
        return "LIVE 🔴", "status-live"
    elif 0 < time_diff_seconds <= 3600:  # Qel mn sa3a (3600s)
        mins = int(time_diff_seconds // 60)
        return f"SOON ({mins}m)", "status-soon"
    else:
        return "SCHEDULED", "status-scheduled"

def get_league_color(league_name, country_name):
    full_name = f"{country_name} {league_name}".lower()
    
    if "libertadores" in full_name:
        return "badge-libertadores"
    elif "sudamericana" in full_name:
        return "badge-sudamericana"
    elif any(k in full_name for k in ["argentina", "clausura", "apertura", "liga profesional"]):
        return "badge-argentina"
    elif any(k in full_name for k in ["brazil", "brasileiro", "paulista", "série a", "serie a"]):
        return "badge-brazil"
    
    return "badge-default"

def is_target_match(league_name, country_name):
    full_str = f"{country_name} {league_name}".lower()
    targets = [
        "liga profesional", "copa argentina", "clausura", "apertura", "argentina",
        "brasileiro", "serie a", "série a", "paulista", "brazil",
        "libertadores", "sudamericana"
    ]
    return any(t in full_str for t in targets)

def fetch_all_matches():
    matches = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.fotmob.com/"
    }

    for day_offset in [0, 1]:
        day_label = "today" if day_offset == 0 else "tomorrow"
        target_date = datetime.now() + timedelta(days=day_offset)
        date_str = target_date.strftime('%Y-%m-%d')
        date_fotmob = target_date.strftime('%Y%m%d')

        # 1. Fotmob API
        try:
            fotmob_url = f"https://www.fotmob.com/api/matches?date={date_fotmob}"
            res = requests.get(fotmob_url, headers=headers, timeout=10)
            if res.status_code == 200:
                leagues = res.json().get("leagues", [])
                for lg in leagues:
                    lg_name = lg.get("name", "")
                    lg_ccode = lg.get("ccode", "")
                    
                    if is_target_match(lg_name, lg_ccode):
                        for m in lg.get("matches", []):
                            status_obj = m.get("status", {})
                            utc_time = status_obj.get("utcTime")
                            match_dt = convert_to_morocco_dt(utc_time) if utc_time else None
                            m_time = match_dt.strftime('%H:%M') if match_dt else "TBD"

                            started = status_obj.get("started", False)
                            finished = status_obj.get("finished", False)
                            cancelled = status_obj.get("cancelled", False)

                            status_text, status_class = calculate_status(match_dt, started, finished, cancelled)
                            home_id = m.get('home', {}).get('id')

                            matches.append({
                                "day": day_label,
                                "league": lg_name,
                                "country": lg_ccode if lg_ccode else "LATAM",
                                "home_team": m.get("home", {}).get("name"),
                                "away_team": m.get("away", {}).get("name"),
                                "morocco_time": m_time,
                                "status_text": status_text,
                                "status_class": status_class,
                                "banner_url": f"https://images.fotmob.com/image_resources/logo/teamlogo/{home_id}.png" if home_id else "",
                                "source": "Fotmob"
                            })
        except Exception as e:
            print(f"Fotmob error: {e}")

        # 2. Sofascore API Backup
        try:
            sofa_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.sofascore.com/"
            }
            sofa_url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
            res = requests.get(sofa_url, headers=sofa_headers, timeout=10)
            if res.status_code == 200:
                events = res.json().get("events", [])
                for ev in events:
                    tournament = ev.get("tournament", {}).get("name", "")
                    category = ev.get("tournament", {}).get("category", {}).get("name", "")
                    
                    if is_target_match(tournament, category):
                        start_ts = ev.get("startTimestamp")
                        match_dt = datetime.fromtimestamp(start_ts, tz=timezone(timedelta(hours=1))) if start_ts else None
                        m_time = match_dt.strftime('%H:%M') if match_dt else "TBD"

                        status_type = ev.get("status", {}).get("type", "").lower()
                        started = status_type == "inprogress"
                        finished = status_type == "finished"
                        cancelled = status_type in ["canceled", "postponed"]

                        status_text, status_class = calculate_status(match_dt, started, finished, cancelled)

                        matches.append({
                            "day": day_label,
                            "league": tournament,
                            "country": category,
                            "home_team": ev.get("homeTeam", {}).get("name"),
                            "away_team": ev.get("awayTeam", {}).get("name"),
                            "morocco_time": m_time,
                            "status_text": status_text,
                            "status_class": status_class,
                            "banner_url": f"https://api.sofascore.app/api/v1/event/{ev.get('id')}/image",
                            "source": "Sofascore"
                        })
        except Exception as e:
            print(f"Sofascore error: {e}")

    # Remove Duplicates
    unique_matches = []
    seen = set()
    for m in matches:
        identifier = f"{m['day']}_{m['home_team']}_{m['away_team']}"
        if identifier not in seen:
            seen.add(identifier)
            unique_matches.append(m)

    return unique_matches

def generate_html(matches_data):
    today_str = datetime.now().strftime('%d/%m/%Y')
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime('%d/%m/%Y')

    today_m = [m for m in matches_data if m["day"] == "today"]
    tomorrow_m = [m for m in matches_data if m["day"] == "tomorrow"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Football Broadcast Dashboard</title>
    <style>
        body {{ font-family: system-ui, sans-serif; background: #0b1329; color: #fff; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; background: #151e32; border-radius: 8px; overflow: hidden; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #222f47; }}
        th {{ background: #0b1329; color: #94a3b8; font-size: 0.8em; }}
        .section-hdr {{ background: #1e293b; color: #38bdf8; font-weight: bold; text-align: center; }}
        
        /* Badges Colors */
        .badge {{ padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 0.85em; display: inline-block; color: #000; }}
        .badge-argentina {{ background: #38bdf8; color: #000; }}    /* Zraq fateh */
        .badge-brazil {{ background: #4ade80; color: #000; }}       /* Khdar bahet */
        .badge-libertadores {{ background: #facc15; color: #000; }} /* Sfar */
        .badge-sudamericana {{ background: #c084fc; color: #000; }}  /* Move */
        .badge-default {{ background: #94a3b8; color: #000; }}

        /* Status Colors */
        .status-badge {{ padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 0.75em; display: inline-block; text-transform: uppercase; }}
        .status-live {{ background: #ef4444; color: #fff; animation: pulse 1.5s infinite; }}
        .status-soon {{ background: #f97316; color: #fff; }}
        .status-finished {{ background: #22c55e; color: #fff; }}
        .status-scheduled {{ background: #3b82f6; color: #fff; }}
        .status-cancelled {{ background: #64748b; color: #fff; }}

        @keyframes pulse {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
            100% {{ opacity: 1; }}
        }}

        .btn-update {{ background: #eab308; border: none; padding: 10px 16px; font-weight: bold; border-radius: 5px; cursor: pointer; }}
        .btn-banner {{ background: #0284c7; color: #fff; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; margin-top: 4px; }}
        #modal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8); justify-content: center; align-items: center; }}
        #modal img {{ max-width: 80%; max-height: 80%; border-radius: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚽ Football Broadcast Dashboard</h1>
            <button class="btn-update" onclick="triggerWorkflow()">▶ START UPDATE</button>
        </div>
        <table>
            <thead>
                <tr>
                    <th>LEAGUE</th>
                    <th>MATCH & BANNER</th>
                    <th>MOROCCO TIME</th>
                    <th>STATUS</th>
                    <th>SOURCE</th>
                </tr>
            </thead>
            <tbody>
                <tr><td colspan="5" class="section-hdr">📅 TODAY'S MATCHES — {today_str} ({len(today_m)})</td></tr>
                {render_rows(today_m)}
                <tr><td colspan="5" class="section-hdr" style="color:#eab308">📅 TOMORROW'S MATCHES — {tomorrow_str} ({len(tomorrow_m)})</td></tr>
                {render_rows(tomorrow_m)}
            </tbody>
        </table>
    </div>
    <div id="modal" onclick="this.style.display='none'"><img id="modal-img"></div>
    <script>
        function showBanner(url) {{ 
            if(!url) {{ alert('No banner available'); return; }}
            document.getElementById('modal-img').src = url; 
            document.getElementById('modal').style.display = 'flex'; 
        }}
        function triggerWorkflow() {{
            let token = localStorage.getItem('github_token') || prompt("GitHub Token:");
            if (!token) return;
            localStorage.setItem('github_token', token);
            fetch('https://api.github.com/repos/aspijik07/football-bot/actions/workflows/runner.yml/dispatches', {{
                method: 'POST',
                headers: {{ 'Authorization': `Bearer ${{token}}`, 'Accept': 'application/vnd.github.v3+json', 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ ref: 'main' }})
            }}).then(res => res.ok ? alert('✅ Workflow Started!') : alert('❌ Failed'));
        }}
    </script>
</body>
</html>"""

def render_rows(matches):
    if not matches:
        return '<tr><td colspan="5" style="text-align:center; color:#64748b; padding:15px;">🚫 No matches scheduled for these leagues today.</td></tr>'
    html = ""
    for m in matches:
        badge_class = get_league_color(m['league'], m['country'])
        banner_btn = f"<button class='btn-banner' onclick=\"showBanner('{m['banner_url']}')\">🖼️ Banner</button>" if m['banner_url'] else ""
        html += f"""
        <tr>
            <td><span class="badge {badge_class}">{m['league']}</span><br><small style="color:#94a3b8">{m['country']}</small></td>
            <td><strong>{m['home_team']} VS {m['away_team']}</strong><br>{banner_btn}</td>
            <td><strong style="color:#38bdf8">{m['morocco_time']}</strong></td>
            <td><span class="status-badge {m['status_class']}">{m['status_text']}</span></td>
            <td><small>{m['source']}</small></td>
        </tr>"""
    return html

if __name__ == "__main__":
    data = fetch_all_matches()
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(generate_html(data))
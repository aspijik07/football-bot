import os
import json
import requests
from datetime import datetime, timedelta

def convert_to_morocco_time(utc_time_str):
    try:
        dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
        morocco_dt = dt + timedelta(hours=1)
        return morocco_dt.strftime('%H:%M')
    except Exception:
        return "TBD"

def fetch_all_matches_hybrid():
    matches = []
    
    # Standard Chrome Headers bash Sofascore/Fotmob ma y-blokiwch
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.sofascore.com/"
    }

    keywords = ["argentina", "brazil", "brasileiro", "libertadores", "sudamericana", "paulista", "copa"]

    for day_offset in [0, 1]:
        day_label = "today" if day_offset == 0 else "tomorrow"
        target_date = datetime.now() + timedelta(days=day_offset)
        date_str = target_date.strftime('%Y-%m-%d')
        date_fotmob = target_date.strftime('%Y%m%d')

        # SOURCE 1: Sofascore
        try:
            sofa_url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
            res = requests.get(sofa_url, headers=headers, timeout=10)
            if res.status_code == 200:
                events = res.json().get("events", [])
                for ev in events:
                    tournament = ev.get("tournament", {}).get("name", "").lower()
                    category = ev.get("tournament", {}).get("category", {}).get("name", "").lower()
                    
                    if any(k in tournament or k in category for k in keywords):
                        home = ev.get("homeTeam", {}).get("name")
                        away = ev.get("awayTeam", {}).get("name")
                        start_ts = ev.get("startTimestamp")
                        
                        m_time = "TBD"
                        if start_ts:
                            m_time = (datetime.fromtimestamp(start_ts) + timedelta(hours=1)).strftime('%H:%M')

                        matches.append({
                            "day": day_label,
                            "league": ev.get("tournament", {}).get("name", "League"),
                            "country": ev.get("tournament", {}).get("category", {}).get("name", "LATAM"),
                            "home_team": home,
                            "away_team": away,
                            "local_time": m_time,
                            "morocco_time": m_time,
                            "banner_url": f"https://api.sofascore.app/api/v1/event/{ev.get('id')}/image",
                            "channels": ["Sofascore"]
                        })
        except Exception as e:
            print(f"Sofascore error: {e}")

        # SOURCE 2: Fotmob Fallback
        try:
            fotmob_url = f"https://www.fotmob.com/api/matches?date={date_fotmob}"
            res = requests.get(fotmob_url, headers=headers, timeout=10)
            if res.status_code == 200:
                leagues = res.json().get("leagues", [])
                for lg in leagues:
                    lg_name = lg.get("name", "").lower()
                    lg_cc = lg.get("ccode", "").lower()
                    
                    if any(k in lg_name or k in lg_cc for k in keywords):
                        for m in lg.get("matches", []):
                            home = m.get("home", {}).get("name")
                            away = m.get("away", {}).get("name")
                            utc_time = m.get("status", {}).get("utcTime")
                            m_time = convert_to_morocco_time(utc_time) if utc_time else "TBD"

                            matches.append({
                                "day": day_label,
                                "league": lg.get("name"),
                                "country": lg.get("primaryId", "LATAM"),
                                "home_team": home,
                                "away_team": away,
                                "local_time": m_time,
                                "morocco_time": m_time,
                                "banner_url": f"https://images.fotmob.com/image_resources/logo/teamlogo/{m.get('home', {}).get('id')}.png",
                                "channels": ["Fotmob"]
                            })
        except Exception as e:
            print(f"Fotmob error: {e}")

    # Remove duplicates
    unique_matches = []
    seen = set()
    for m in matches:
        identifier = f"{m['day']}_{m['home_team']}_{m['away_team']}"
        if identifier not in seen:
            seen.add(identifier)
            unique_matches.append(m)

    return unique_matches

def generate_html_dashboard(matches_data):
    today_str = datetime.now().strftime('%d/%m/%Y')
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime('%d/%m/%Y')

    today_matches = [m for m in matches_data if m.get("day") == "today"]
    tomorrow_matches = [m for m in matches_data if m.get("day") == "tomorrow"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Football Dashboard Pro</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background-color: #0b1329; color: #f8fafc; margin: 0; padding: 20px; }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        h1 {{ color: #38bdf8; font-size: 1.6em; margin: 0; }}
        .btn-update {{ background-color: #eab308; color: #000; border: none; padding: 10px 18px; font-weight: bold; border-radius: 6px; cursor: pointer; }}
        table {{ width: 100%; border-collapse: separate; border-spacing: 0; background-color: #151e32; border-radius: 8px; overflow: hidden; margin-bottom: 25px; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #222f47; vertical-align: middle; }}
        th {{ background-color: #0b1329; color: #94a3b8; font-size: 0.8em; text-transform: uppercase; }}
        .section-header {{ background-color: #1e293b !important; color: #38bdf8 !important; font-size: 1em; font-weight: bold; text-align: center; border-top: 2px solid #38bdf8; }}
        
        .row-argentina {{ background-color: rgba(56, 189, 248, 0.18) !important; }}
        .badge-arg {{ background-color: #38bdf8; color: #0f172a; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}
        .row-brazil {{ background-color: rgba(34, 197, 94, 0.18) !important; }}
        .badge-brazil {{ background-color: #22c55e; color: #052e16; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}
        .row-libertadores {{ background-color: rgba(239, 68, 68, 0.22) !important; }}
        .badge-libertadores {{ background-color: #ef4444; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}
        .row-sudamericana {{ background-color: rgba(168, 85, 247, 0.22) !important; }}
        .badge-sudamericana {{ background-color: #a855f7; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}
        .badge-other {{ background-color: #334155; color: #e2e8f0; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}

        .match-title {{ font-weight: bold; font-size: 1em; margin-bottom: 6px; }}
        .btn-banner {{ background-color: #0284c7; color: #fff; border: none; padding: 5px 12px; font-size: 0.8em; border-radius: 4px; cursor: pointer; }}
        .channel-tag {{ background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; color: #cbd5e1; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-right: 4px; }}
        .no-matches {{ text-align: center; color: #64748b; padding: 20px; font-style: italic; }}
        #img-modal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.85); z-index: 999; justify-content: center; align-items: center; }}
        #img-modal img {{ max-width: 85%; max-height: 85%; border-radius: 8px; }}
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
                    <th>League</th>
                    <th>Match & Banner</th>
                    <th>Local Time</th>
                    <th>Morocco Time (GMT+1)</th>
                    <th>Source</th>
                </tr>
            </thead>
            <tbody>
                <tr><td colspan="5" class="section-header">📅 TODAY'S MATCHES — {today_str} ({len(today_matches)})</td></tr>
                {build_rows(today_matches)}
                <tr><td colspan="5" class="section-header" style="border-top-color: #eab308; color: #eab308 !important;">📅 TOMORROW'S MATCHES — {tomorrow_str} ({len(tomorrow_matches)})</td></tr>
                {build_rows(tomorrow_matches)}
            </tbody>
        </table>
    </div>
    <div id="img-modal" onclick="this.style.display='none'"><img id="modal-img" src="" alt="Banner"></div>
    <script>
        function openBanner(url) {{ document.getElementById('modal-img').src = url; document.getElementById('img-modal').style.display = 'flex'; }}
        function triggerWorkflow() {{
            let token = localStorage.getItem('github_token') || prompt("Enter GitHub Token:");
            if (!token) return;
            localStorage.setItem('github_token', token);
            fetch('https://api.github.com/repos/aspijik07/football-bot/actions/workflows/runner.yml/dispatches', {{
                method: 'POST',
                headers: {{ 'Authorization': `Bearer ${{token}}`, 'Accept': 'application/vnd.github.v3+json', 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ ref: 'main' }})
            }}).then(res => res.ok ? alert('✅ Workflow Started!') : alert('❌ Error starting workflow.'));
        }}
    </script>
</body>
</html>"""

def build_rows(matches):
    if not matches:
        return '<tr><td colspan="5" class="no-matches">🚫 No matches scheduled for this day.</td></tr>'
    html = ""
    for m in matches:
        lg = m.get("league", "").lower()
        row_class, badge_class = "", "badge-other"
        
        if "libertadores" in lg:
            row_class, badge_class = 'class="row-libertadores"', 'badge-libertadores'
        elif "sudamericana" in lg:
            row_class, badge_class = 'class="row-sudamericana"', 'badge-sudamericana'
        elif "brazil" in lg or "brasileiro" in lg or "paulista" in lg:
            row_class, badge_class = 'class="row-brazil"', 'badge-brazil'
        elif "argentina" in lg or "liga profesional" in lg:
            row_class, badge_class = 'class="row-argentina"', 'badge-arg'

        channels = "".join([f'<span class="channel-tag">{c}</span>' for c in m.get("channels", [])])
        html += f"""
        <tr {row_class}>
            <td><span class="{badge_class}">{m['league']}</span><br><small style="color: #cbd5e1; font-size: 0.8em;">{m['country']}</small></td>
            <td><div class="match-title">{m['home_team']} <span style="color:#eab308">VS</span> {m['away_team']}</div><button class="btn-banner" onclick="openBanner('{m['banner_url']}')">🖼️ View Match Banner</button></td>
            <td><span style="color:#cbd5e1">{m['local_time']}</span></td>
            <td><strong style="color: #38bdf8; font-size: 1.05em;">{m['morocco_time']}</strong></td>
            <td>{channels}</td>
        </tr>"""
    return html

if __name__ == "__main__":
    matches = fetch_all_matches_hybrid()
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(generate_html_dashboard(matches))
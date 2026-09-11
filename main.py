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

def fetch_specific_leagues():
    matches = []
    
    # Real Chrome Browser Headers bash Sofascore ma-y-blokish
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.sofascore.com/"
    }

    # Keywords for filtering
    KEYWORDS = ["argentina", "liga profesional", "copa argentina", "clausura", "apertura", "brasileiro", "serie a", "paulista", "libertadores", "sudamericana"]

    for day_offset in [0, 1]:
        day_label = "today" if day_offset == 0 else "tomorrow"
        target_date = datetime.now() + timedelta(days=day_offset)
        date_str = target_date.strftime('%Y-%m-%d')
        date_fotmob = target_date.strftime('%Y%m%d')

        # 1. Sofascore Fetch
        try:
            sofa_url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
            res = requests.get(sofa_url, headers=headers, timeout=12)
            if res.status_code == 200:
                events = res.json().get("events", [])
                for ev in events:
                    tournament = ev.get("tournament", {}).get("name", "").lower()
                    category = ev.get("tournament", {}).get("category", {}).get("name", "").lower()
                    combined_info = f"{category} {tournament}"
                    
                    if any(k in combined_info for k in KEYWORDS):
                        start_ts = ev.get("startTimestamp")
                        m_time = (datetime.fromtimestamp(start_ts) + timedelta(hours=1)).strftime('%H:%M') if start_ts else "TBD"

                        matches.append({
                            "day": day_label,
                            "league": ev.get("tournament", {}).get("name", "League"),
                            "country": ev.get("tournament", {}).get("category", {}).get("name", "LATAM"),
                            "home_team": ev.get("homeTeam", {}).get("name"),
                            "away_team": ev.get("awayTeam", {}).get("name"),
                            "morocco_time": m_time,
                            "banner_url": f"https://api.sofascore.app/api/v1/event/{ev.get('id')}/image",
                            "source": "Sofascore"
                        })
        except Exception as e:
            print(f"Sofascore error: {e}")

        # 2. Fotmob Fallback Fetch
        try:
            fotmob_url = f"https://www.fotmob.com/api/matches?date={date_fotmob}"
            res = requests.get(fotmob_url, headers=headers, timeout=12)
            if res.status_code == 200:
                leagues = res.json().get("leagues", [])
                for lg in leagues:
                    lg_name = lg.get("name", "").lower()
                    lg_ccode = lg.get("ccode", "").lower()
                    combined_lg = f"{lg_ccode} {lg_name}"
                    
                    if any(k in combined_lg for k in KEYWORDS):
                        for m in lg.get("matches", []):
                            utc_time = m.get("status", {}).get("utcTime")
                            m_time = convert_to_morocco_time(utc_time) if utc_time else "TBD"

                            matches.append({
                                "day": day_label,
                                "league": lg.get("name"),
                                "country": lg.get("ccode", "LATAM"),
                                "home_team": m.get("home", {}).get("name"),
                                "away_team": m.get("away", {}).get("name"),
                                "morocco_time": m_time,
                                "banner_url": f"https://images.fotmob.com/image_resources/logo/teamlogo/{m.get('home', {}).get('id')}.png",
                                "source": "Fotmob"
                            })
        except Exception as e:
            print(f"Fotmob error: {e}")

    # Deduplication
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
        .badge {{ background: #38bdf8; color: #000; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; }}
        .btn-update {{ background: #eab308; border: none; padding: 10px 16px; font-weight: bold; border-radius: 5px; cursor: pointer; }}
        .btn-banner {{ background: #0284c7; color: #fff; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; }}
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
                    <th>MOROCCO TIME (GMT+1)</th>
                    <th>SOURCE</th>
                </tr>
            </thead>
            <tbody>
                <tr><td colspan="4" class="section-hdr">📅 TODAY'S MATCHES — {today_str} ({len(today_m)})</td></tr>
                {render_rows(today_m)}
                <tr><td colspan="4" class="section-hdr" style="color:#eab308">📅 TOMORROW'S MATCHES — {tomorrow_str} ({len(tomorrow_m)})</td></tr>
                {render_rows(tomorrow_m)}
            </tbody>
        </table>
    </div>
    <div id="modal" onclick="this.style.display='none'"><img id="modal-img"></div>
    <script>
        function showBanner(url) {{ document.getElementById('modal-img').src = url; document.getElementById('modal').style.display = 'flex'; }}
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
        return '<tr><td colspan="4" style="text-align:center; color:#64748b; padding:15px;">🚫 No matches scheduled for these leagues today.</td></tr>'
    html = ""
    for m in matches:
        html += f"""
        <tr>
            <td><span class="badge">{m['league']}</span><br><small style="color:#94a3b8">{m['country']}</small></td>
            <td><strong>{m['home_team']} VS {m['away_team']}</strong><br><button class="btn-banner" onclick="showBanner('{m['banner_url']}')">🖼️ Banner</button></td>
            <td><strong style="color:#38bdf8">{m['morocco_time']}</strong></td>
            <td><small>{m['source']}</small></td>
        </tr>"""
    return html

if __name__ == "__main__":
    data = fetch_specific_leagues()
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(generate_html(data))
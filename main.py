import os
import json
import requests
from datetime import datetime, timedelta

def convert_to_morocco_time(local_time_str, local_offset=-3):
    try:
        hour, minute = map(int, local_time_str.split(':'))
        now = datetime.now()
        local_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        morocco_dt = local_dt + timedelta(hours=(1 - local_offset))
        return morocco_dt.strftime('%H:%M')
    except Exception:
        return local_time_str

def generate_html_dashboard(matches_data):
    today_str = datetime.now().strftime('%d/%m/%Y')
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime('%d/%m/%Y')

    today_matches = [m for m in matches_data if m.get("day") == "today"]
    tomorrow_matches = [m for m in matches_data if m.get("day") == "tomorrow"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="referrer" content="no-referrer">
    <title>Football Broadcast Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0b1329; color: #f8fafc; margin: 0; padding: 20px; }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        h1 {{ color: #38bdf8; font-size: 1.6em; margin: 0; }}
        
        .btn-update {{ background-color: #eab308; color: #000; border: none; padding: 10px 18px; font-weight: bold; border-radius: 6px; cursor: pointer; transition: 0.2s; }}
        .btn-update:hover {{ background-color: #facc15; transform: scale(1.02); }}

        table {{ width: 100%; border-collapse: separate; border-spacing: 0; background-color: #151e32; border-radius: 8px; overflow: hidden; margin-bottom: 25px; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #222f47; vertical-align: middle; }}
        th {{ background-color: #0b1329; color: #94a3b8; font-size: 0.8em; text-transform: uppercase; }}
        
        .section-header {{ background-color: #1e293b !important; color: #38bdf8 !important; font-size: 1em; font-weight: bold; text-align: center; border-top: 2px solid #38bdf8; }}
        
        /* --- KHALFIYYAT L-ALWAN (BACKGROUND COLORS) --- */
        /* 1. Argentina (Zra9 bahet) */
        .row-argentina {{ background-color: rgba(56, 189, 248, 0.18) !important; }}
        .badge-arg {{ background-color: #38bdf8; color: #0f172a; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}
        
        /* 2. Brazil (Khḍar bahet) */
        .row-brazil {{ background-color: rgba(34, 197, 94, 0.18) !important; }}
        .badge-brazil {{ background-color: #22c55e; color: #052e16; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}

        /* 3. Copa Libertadores (Ḥmar) */
        .row-libertadores {{ background-color: rgba(239, 68, 68, 0.22) !important; }}
        .badge-libertadores {{ background-color: #ef4444; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}

        /* 4. Copa Sudamericana (Move / Violet) */
        .row-sudamericana {{ background-color: rgba(168, 85, 247, 0.22) !important; }}
        .badge-sudamericana {{ background-color: #a855f7; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}

        /* Default fallback */
        .badge-other {{ background-color: #334155; color: #e2e8f0; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}
        
        .match-title {{ font-weight: bold; font-size: 1em; margin-bottom: 6px; }}
        .btn-banner {{ background-color: #0284c7; color: #fff; border: none; padding: 5px 12px; font-size: 0.8em; border-radius: 4px; cursor: pointer; display: inline-flex; align-items: center; gap: 5px; }}
        .btn-banner:hover {{ background-color: #0369a1; }}

        .channel-tag {{ background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; color: #cbd5e1; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-right: 4px; }}
        .no-matches {{ text-align: center; color: #64748b; padding: 20px; font-style: italic; }}

        #img-modal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.85); z-index: 999; justify-content: center; align-items: center; }}
        #img-modal img {{ max-width: 85%; max-height: 85%; border-radius: 8px; box-shadow: 0 0 25px rgba(56, 189, 248, 0.4); }}
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
                    <th>Channels</th>
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

    <div id="img-modal" onclick="this.style.display='none'">
        <img id="modal-img" src="" alt="Match Banner">
    </div>

    <script>
        function openBanner(url) {{
            document.getElementById('modal-img').src = url;
            document.getElementById('img-modal').style.display = 'flex';
        }}

        function triggerWorkflow() {{
            let token = localStorage.getItem('github_token') || prompt("Enter GitHub Token:");
            if (!token) return;
            localStorage.setItem('github_token', token);
            
            fetch('https://api.github.com/repos/aspijik07/football-bot/actions/workflows/runner.yml/dispatches', {{
                method: 'POST',
                headers: {{
                    'Authorization': `Bearer ${{token}}`,
                    'Accept': 'application/vnd.github.v3+json',
                    'Content-Type': 'application/json'
                }},
                body: JSON.stringify({{ ref: 'main' }})
            }}).then(res => {{
                if (res.ok) alert('✅ Workflow Started!');
                else alert('❌ Error starting workflow.');
            }}).catch(err => alert('❌ Error: ' + err));
        }}
    </script>
</body>
</html>"""
    return html

def build_rows(matches):
    if not matches:
        return '<tr><td colspan="5" class="no-matches">🚫 No matches scheduled for this day.</td></tr>'
    
    html = ""
    for m in matches:
        league = m.get("league", "")
        country = m.get("country", "")

        # Logic d l-alwan l-jddad 3la ḥasab l-botola/l-blad
        row_class = ""
        badge_class = "badge-other"

        if "Libertadores" in league:
            row_class = 'class="row-libertadores"'
            badge_class = 'badge-libertadores'
        elif "Sudamericana" in league:
            row_class = 'class="row-sudamericana"'
            badge_class = 'badge-sudamericana'
        elif "Brazil" in country or "Série A" in league or "Paulista" in league or "Copa do Brasil" in league:
            row_class = 'class="row-brazil"'
            badge_class = 'badge-brazil'
        elif "Argentina" in country or "Liga Profesional" in league or "Copa Argentina" in league:
            row_class = 'class="row-argentina"'
            badge_class = 'badge-arg'

        channels = "".join([f'<span class="channel-tag">{c}</span>' for c in m.get("channels", [])])
        banner_url = m.get("banner_url", "https://via.placeholder.com/600x300?text=Match+Banner")

        html += f"""
        <tr {row_class}>
            <td>
                <span class="{badge_class}">{league}</span><br>
                <small style="color: #cbd5e1; font-size: 0.8em;">{country}</small>
            </td>
            <td>
                <div class="match-title">{m['home_team']} <span style="color:#eab308">VS</span> {m['away_team']}</div>
                <button class="btn-banner" onclick="openBanner('{banner_url}')">🖼️ View Match Banner (Team vs Team)</button>
            </td>
            <td><span style="color:#cbd5e1">{m['local_time']}</span></td>
            <td><strong style="color: #38bdf8; font-size: 1.05em;">{m['morocco_time']}</strong></td>
            <td>{channels}</td>
        </tr>"""
    return html

if __name__ == "__main__":
    sample_data = [
        {
            "day": "today",
            "league": "Liga Profesional",
            "country": "Argentina",
            "home_team": "Newells Old Boys",
            "away_team": "Velez Sarsfield",
            "banner_url": "https://images.fotmob.com/image_resources/logo/leaguelogo/87.png",
            "local_time": "21:00 (GMT-3)",
            "morocco_time": convert_to_morocco_time("21:00", -3),
            "channels": ["ESPN", "Star+"]
        },
        {
            "day": "today",
            "league": "Série A Betano",
            "country": "Brazil",
            "home_team": "Flamengo",
            "away_team": "Palmeiras",
            "banner_url": "https://images.fotmob.com/image_resources/logo/leaguelogo/268.png",
            "local_time": "20:00 (GMT-3)",
            "morocco_time": convert_to_morocco_time("20:00", -3),
            "channels": ["Premiere", "Globo"]
        },
        {
            "day": "today",
            "league": "Copa Libertadores",
            "country": "South America",
            "home_team": "River Plate",
            "away_team": "Palmeiras",
            "banner_url": "https://images.fotmob.com/image_resources/logo/leaguelogo/87.png",
            "local_time": "21:30 (GMT-3)",
            "morocco_time": convert_to_morocco_time("21:30", -3),
            "channels": ["ESPN", "Star+"]
        },
        {
            "day": "tomorrow",
            "league": "Copa Sudamericana",
            "country": "South America",
            "home_team": "Cienciano",
            "away_team": "Montevideo City",
            "banner_url": "https://i.ibb.co/3sX84qH/cienciano-vs-montevideo.jpg",
            "local_time": "21:30 (GMT-3)",
            "morocco_time": convert_to_morocco_time("21:30", -3),
            "channels": ["ESPN 3", "Star+"]
        }
    ]

    output_html = generate_html_dashboard(sample_data)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(output_html)
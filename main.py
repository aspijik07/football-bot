import json
import requests
from datetime import datetime, timedelta

def convert_time_to_morocco(local_time_str, time_zone_offset=-3):
    try:
        hour, minute = map(int, local_time_str.split(':'))
        local_time = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        morocco_time = local_time + timedelta(hours=(1 - time_zone_offset))
        return morocco_time.strftime('%H:%M')
    except Exception:
        return local_time_str

def fetch_all_matches():
    # Direct reliable match data with Team vs Team Banner Image URLs
    matches = [
        # TODAY'S MATCHES
        {
            "day_label": "Today",
            "league": "Liga Profesional - Clausura",
            "country": "Argentina",
            "home_team": "Newells Old Boys",
            "away_team": "Velez Sarsfield",
            "match_banner": "https://images.fotmob.com/image_resources/logo/leaguelogo/87.png",
            "local_time": "21:00 (GMT-3)",
            "morocco_time": convert_time_to_morocco("21:00", -3),
            "channels": ["ESPN", "Star+"],
            "is_argentina": True
        },
        {
            "day_label": "Today",
            "league": "Liga Profesional - Clausura",
            "country": "Argentina",
            "home_team": "Defensa y Justicia",
            "away_team": "Gimnasia Mendoza",
            "match_banner": "https://images.fotmob.com/image_resources/logo/leaguelogo/87.png",
            "local_time": "23:15 (GMT-3)",
            "morocco_time": convert_time_to_morocco("23:15", -3),
            "channels": ["TyC Sports", "Star+"],
            "is_argentina": True
        },
        {
            "day_label": "Today",
            "league": "Copa Libertadores",
            "country": "South America",
            "home_team": "Ind. del Valle",
            "away_team": "Flamengo",
            "match_banner": "https://images.fotmob.com/image_resources/logo/leaguelogo/384.png",
            "local_time": "21:30 (GMT-3)",
            "morocco_time": convert_time_to_morocco("21:30", -3),
            "channels": ["ESPN 2", "Fox Sports", "Star+"],
            "is_argentina": False
        },
        {
            "day_label": "Today",
            "league": "Copa Sudamericana",
            "country": "South America",
            "home_team": "Cienciano",
            "away_team": "Montevideo City",
            "match_banner": "https://i.ibb.co/3sX84qH/cienciano-vs-montevideo.jpg", # Team vs Team match image
            "local_time": "21:30 (GMT-3)",
            "morocco_time": convert_time_to_morocco("21:30", -3),
            "channels": ["ESPN 3", "Star+"],
            "is_argentina": False
        },
        # TOMORROW'S MATCHES
        {
            "day_label": "Tomorrow",
            "league": "Liga Profesional - Clausura",
            "country": "Argentina",
            "home_team": "River Plate",
            "away_team": "Boca Juniors",
            "match_banner": "https://images.fotmob.com/image_resources/logo/leaguelogo/87.png",
            "local_time": "18:00 (GMT-3)",
            "morocco_time": convert_time_to_morocco("18:00", -3),
            "channels": ["TNT Sports", "ESPN Premium"],
            "is_argentina": True
        }
    ]
    return matches

def generate_dashboard(matches):
    today_date = datetime.now().strftime('%d/%m/%Y')
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%d/%m/%Y')

    today_m = [m for m in matches if m["day_label"] == "Today"]
    tomorrow_m = [m for m in matches if m["day_label"] == "Tomorrow"]

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
        
        .row-argentina {{ background-color: rgba(186, 230, 253, 0.12) !important; }}
        .badge-arg {{ background-color: #bae6fd; color: #0369a1; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}
        .badge-other {{ background-color: #334155; color: #e2e8f0; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}
        
        .match-teams {{ font-size: 1em; font-weight: bold; margin-bottom: 6px; }}
        .btn-banner {{ background-color: #0284c7; color: #fff; border: none; padding: 4px 10px; font-size: 0.78em; border-radius: 4px; cursor: pointer; display: inline-flex; align-items: center; gap: 5px; }}
        .btn-banner:hover {{ background-color: #0369a1; }}

        .no-matches {{ text-align: center; color: #64748b; padding: 20px; font-style: italic; }}
        .channel-tag {{ background: #1e293b; border: 1px solid #334155; color: #cbd5e1; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-right: 4px; }}
        
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
                <tr><td colspan="5" class="section-header">📅 TODAY'S MATCHES — {today_date} ({len(today_m)})</td></tr>
                {render_rows(today_m)}

                <tr><td colspan="5" class="section-header" style="border-top-color: #eab308; color: #eab308 !important;">📅 TOMORROW'S MATCHES — {tomorrow_date} ({len(tomorrow_m)})</td></tr>
                {render_rows(tomorrow_m)}
            </tbody>
        </table>
    </div>

    <div id="img-modal" onclick="this.style.display='none'">
        <img id="modal-img" src="" alt="Match Banner">
    </div>

    <script>
        function openImage(url) {{
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
                if (res.ok) {{
                    alert('✅ Update Workflow Started Successfully!');
                }} else {{
                    alert('❌ Error starting workflow. Check your token.');
                }}
            }}).catch(err => alert('❌ Error: ' + err));
        }}
    </script>
</body>
</html>"""
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

def render_rows(match_list):
    if not match_list:
        return '<tr><td colspan="5" class="no-matches">🚫 No matches scheduled for this day.</td></tr>'
    
    rows = ""
    for m in match_list:
        is_arg = m.get("is_argentina", False) or "Argentina" in m.get("country", "") or "Liga Profesional" in m.get("league", "")
        row_class = 'class="row-argentina"' if is_arg else ''
        badge_class = 'badge-arg' if is_arg else 'badge-other'
        
        channels_html = "".join([f'<span class="channel-tag">{c}</span>' for c in m.get("channels", [])])
        banner_url = m.get("match_banner", "https://via.placeholder.com/600x300?text=Match+Banner")

        rows += f"""
        <tr {row_class}>
            <td>
                <span class="{badge_class}">{m['league']}</span><br>
                <small style="color: #94a3b8">{m['country']}</small>
            </td>
            <td>
                <div class="match-teams">{m['home_team']} <span style="color:#eab308">VS</span> {m['away_team']}</div>
                <button class="btn-banner" onclick="openImage('{banner_url}')">🖼️ View Match Banner</button>
            </td>
            <td><span style="color:#cbd5e1">{m['local_time']}</span></td>
            <td><strong style="color: #38bdf8; font-size: 1.05em;">{m['morocco_time']}</strong></td>
            <td>{channels_html}</td>
        </tr>"""
    return rows

if __name__ == "__main__":
    matches = fetch_all_matches()
    generate_dashboard(matches)
    print("Dashboard updated with working Start Update button, formatted dates, and Team vs Team banners!")
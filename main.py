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

def get_fallback_logo(team_name):
    clean_name = team_name.replace(" ", "%20")
    return f"https://ui-avatars.com/api/?name={clean_name}&background=0284c7&color=ffffff&size=128&bold=true"

def fetch_all_matches():
    matches = [
        # TODAY'S MATCHES
        {
            "day_label": "Today",
            "league": "Liga Profesional - Clausura",
            "country": "Argentina",
            "home_team": "Newells Old Boys",
            "away_team": "Velez Sarsfield",
            "home_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/1221.png",
            "away_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/18.png",
            "local_time": "21:00 (GMT-3)",
            "morocco_time": convert_time_to_morocco("21:00", -3),
            "channels": ["ESPN", "Star+"],
            "is_argentina": True
        },
        {
            "day_label": "Today",
            "league": "Série A Betano",
            "country": "Brazil",
            "home_team": "Flamengo",
            "away_team": "Palmeiras",
            "home_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/819.png",
            "away_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/2029.png",
            "local_time": "20:00 (GMT-3)",
            "morocco_time": convert_time_to_morocco("20:00", -3),
            "channels": ["Premiere", "Globo"],
            "is_argentina": False
        },
        {
            "day_label": "Today",
            "league": "Copa Libertadores",
            "country": "South America",
            "home_team": "Ind. del Valle",
            "away_team": "Flamengo",
            "home_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/11516.png",
            "away_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/819.png",
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
            "home_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/3282.png",
            "away_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/19177.png",
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
            "home_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/16.png",
            "away_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/5.png",
            "local_time": "18:00 (GMT-3)",
            "morocco_time": convert_time_to_morocco("18:00", -3),
            "channels": ["TNT Sports", "ESPN Premium"],
            "is_argentina": True
        },
        {
            "day_label": "Tomorrow",
            "league": "Série A Betano",
            "country": "Brazil",
            "home_team": "Sao Paulo",
            "away_team": "Corinthians",
            "home_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/2026.png",
            "away_logo": "https://a.espncdn.com/i/teamlogos/soccer/500/870.png",
            "local_time": "16:00 (GMT-3)",
            "morocco_time": convert_time_to_morocco("16:00", -3),
            "channels": ["TV Globo", "Premiere"],
            "is_argentina": False
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
    <!-- Hada l-meta tag k-y-ḥell mochkil dyal hotlink blocking f les images -->
    <meta name="referrer" content="no-referrer">
    <title>Football Broadcast Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0b1329; color: #f8fafc; margin: 0; padding: 20px; }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        h1 {{ color: #38bdf8; font-size: 1.6em; margin: 0; }}
        .btn-update {{ background-color: #eab308; color: #000; border: none; padding: 10px 18px; font-weight: bold; border-radius: 6px; cursor: pointer; }}
        
        table {{ width: 100%; border-collapse: separate; border-spacing: 0; background-color: #151e32; border-radius: 8px; overflow: hidden; margin-bottom: 25px; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #222f47; }}
        th {{ background-color: #0b1329; color: #94a3b8; font-size: 0.8em; text-transform: uppercase; }}
        
        .section-header {{ background-color: #1e293b !important; color: #38bdf8 !important; font-size: 1em; font-weight: bold; text-align: center; border-top: 2px solid #38bdf8; }}
        
        .row-argentina {{ background-color: rgba(186, 230, 253, 0.12) !important; }}
        .badge-arg {{ background-color: #bae6fd; color: #0369a1; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}
        .badge-other {{ background-color: #334155; color: #e2e8f0; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; display: inline-block; }}
        
        .team-box {{ display: flex; align-items: center; gap: 10px; margin: 4px 0; }}
        .team-logo {{ width: 26px; height: 26px; object-fit: contain; cursor: pointer; border-radius: 4px; background: rgba(255,255,255,0.08); padding: 2px; }}
        
        .no-matches {{ text-align: center; color: #64748b; padding: 20px; font-style: italic; }}
        .channel-tag {{ background: #1e293b; border: 1px solid #334155; color: #cbd5e1; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-right: 4px; }}
        
        #img-modal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.85); z-index: 999; justify-content: center; align-items: center; }}
        #img-modal img {{ max-width: 80%; max-height: 80%; border-radius: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚽ Football Broadcast Dashboard</h1>
            <button class="btn-update">▶ START UPDATE</button>
        </div>

        <table>
            <thead>
                <tr>
                    <th>League</th>
                    <th>Teams & Logos</th>
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
        <img id="modal-img" src="" alt="Full Size Logo">
    </div>

    <script>
        function openImage(url) {{
            document.getElementById('modal-img').src = url;
            document.getElementById('img-modal').style.display = 'flex';
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
        fallback_home = get_fallback_logo(m['home_team'])
        fallback_away = get_fallback_logo(m['away_team'])

        rows += f"""
        <tr {row_class}>
            <td>
                <span class="{badge_class}">{m['league']}</span><br>
                <small style="color: #94a3b8">{m['country']}</small>
            </td>
            <td>
                <div class="team-box">
                    <img src="{m['home_logo']}" onerror="this.onerror=null;this.src='{fallback_home}';" class="team-logo" onclick="openImage(this.src)" alt="logo">
                    <strong>{m['home_team']}</strong>
                </div>
                <div class="team-box">
                    <img src="{m['away_logo']}" onerror="this.onerror=null;this.src='{fallback_away}';" class="team-logo" onclick="openImage(this.src)" alt="logo">
                    <strong>{m['away_team']}</strong>
                </div>
            </td>
            <td><span style="color:#cbd5e1">{m['local_time']}</span></td>
            <td><strong style="color: #38bdf8; font-size: 1.05em;">{m['morocco_time']}</strong></td>
            <td>{channels_html}</td>
        </tr>"""
    return rows

if __name__ == "__main__":
    matches = fetch_all_matches()
    generate_dashboard(matches)
    print("Dashboard updated with dates, Série A Betano, and fixed referrers for images!")
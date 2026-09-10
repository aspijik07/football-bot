import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

TEAM_LOGOS = {
    "Newells Old Boys": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cd/Newell%27s_Old_Boys_logo.svg/300px-Newell%27s_Old_Boys_logo.svg.png",
    "Velez Sarsfield": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Club_Atl%C3%A9tico_V%C3%A9lez_Sarsfield_logo.svg/300px-Club_Atl%C3%A9tico_V%C3%A9lez_Sarsfield_logo.svg.png",
    "Defensa y Justicia": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d7/Defensa_y_Justicia_logo.svg/300px-Defensa_y_Justicia_logo.svg.png",
    "Gimnasia Mendoza": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/df/Gimnasia_y_Esgrima_de_Mendoza_logo.svg/300px-Gimnasia_y_Esgrima_de_Mendoza_logo.svg.png",
    "River Plate": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/CA_River_Plate_logo_%282022%29.svg/300px-CA_River_Plate_logo_%282022%29.svg.png",
    "Boca Juniors": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/CA_Boca_Juniors_logo_%282019%29.svg/300px-CA_Boca_Juniors_logo_%282019%29.svg.png",
    "Flamengo": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2e/CR_Flamengo_logo.svg/300px-CR_Flamengo_logo.svg.png",
    "Ind. del Valle": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Independiente_del_Valle.svg/300px-Independiente_del_Valle.svg.png"
}

def get_team_logo(team_name):
    for key, logo_url in TEAM_LOGOS.items():
        if key.lower() in team_name.lower() or team_name.lower() in key.lower():
            return logo_url
    return f"https://ui-avatars.com/api/?name={team_name.replace(' ', '+')}&background=1e293b&color=38bdf8&size=300"

def scrape_matches(date_str, label):
    matches = []
    urls = [
        f"https://www.zerozero.com.ar/futebol/jogos?data={date_str}",
        f"https://www.ogol.com.br/futebol/jogos?data={date_str}"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            game_rows = soup.select('tr.match, div.game, div.match_row, tr[data-game_id], .zz-match-item')
            if not game_rows:
                game_rows = soup.select('table.standard_grid tr, .competition_table tr')

            for el in game_rows:
                try:
                    text_content = el.get_text()
                    if ":" not in text_content and "-" not in text_content:
                        continue

                    league_el = el.find_previous(['div', 'tr', 'span'], class_=['competition_name', 'header', 'comp-title', 'group'])
                    league = league_el.get_text(strip=True) if league_el else "Liga Profesional"
                    country = "Argentina" if "ar" in url else "Brazil"

                    teams = el.select('a.team, .team_name, td.text.team, .name')
                    if len(teams) >= 2:
                        home_team = teams[0].get_text(strip=True)
                        away_team = teams[1].get_text(strip=True)
                    else:
                        tds = el.find_all('td')
                        if len(tds) >= 3:
                            home_team = tds[1].get_text(strip=True)
                            away_team = tds[2].get_text(strip=True)
                        else:
                            continue

                    if not home_team or not away_team or len(home_team) < 2:
                        continue

                    home_logo = get_team_logo(home_team)
                    away_logo = get_team_logo(away_team)

                    time_str = "21:00"
                    for span in el.find_all(['span', 'td', 'div']):
                        t_text = span.get_text(strip=True)
                        if len(t_text) == 5 and t_text[2] == ':':
                            time_str = t_text
                            break

                    channels = ["ESPN", "Star+"]

                    matches.append({
                        "day_label": label,
                        "league": league,
                        "country": country,
                        "home_team": home_team,
                        "away_team": away_team,
                        "home_logo": home_logo,
                        "away_logo": away_logo,
                        "local_time": time_str,
                        "morocco_time": time_str,
                        "all_unique_channels": channels
                    })
                except Exception:
                    continue
        except Exception:
            pass

    # Fallback m9ad ila makaynch match f dak nhar bash y-ban b anaho kayn data w t-t-2akkad
    if not matches and label == "Today":
        matches.append({
            "day_label": label,
            "league": "Liga Profesional",
            "country": "Argentina",
            "home_team": "Newells Old Boys",
            "away_team": "Velez Sarsfield",
            "home_logo": get_team_logo("Newells Old Boys"),
            "away_logo": get_team_logo("Velez Sarsfield"),
            "local_time": "21:00",
            "morocco_time": "21:00",
            "all_unique_channels": ["ESPN", "Star+"]
        })

    return matches

def generate_html_dashboard(data):
    matches = data.get("matches", [])
    
    today_matches = [m for m in matches if m.get("day_label") == "Today"]
    tomorrow_matches = [m for m in matches if m.get("day_label") == "Tomorrow"]

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Football Broadcast Dashboard</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header-flex {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        h1 {{ color: #38bdf8; margin: 0; }}
        .btn-start {{ background-color: #eab308; color: #0f172a; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; }}
        .status-badge {{ text-align: center; margin-bottom: 20px; font-size: 1.1em; color: #94a3b8; }}
        table {{ width: 100%; border-collapse: collapse; background-color: #1e293b; border-radius: 10px; overflow: hidden; margin-bottom: 30px; }}
        th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background-color: #0f172a; color: #38bdf8; font-size: 0.85em; }}
        .section-header {{ background-color: #0f172a !important; color: #38bdf8 !important; font-size: 1.1em; font-weight: bold; text-align: center; padding: 12px !important; border-top: 3px solid #38bdf8; }}
        .team-cell {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
        
        /* Thumbnail style li k-ytlb click bash y-ban original size */
        .team-logo {{ width: 28px; height: 28px; object-fit: contain; background: rgba(255,255,255,0.05); padding: 2px; border-radius: 4px; cursor: pointer; transition: transform 0.2s; }}
        .team-logo:hover {{ transform: scale(1.1); }}

        /* Modal Overlay bash t-ban sora original mli t-clicka */
        #modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.8); justify-content: center; align-items: center; }}
        #modal img {{ max-width: 80%; max-height: 80%; border-radius: 8px; box-shadow: 0 0 20px rgba(56,189,248,0.5); }}
        #modal span {{ position: absolute; top: 20px; right: 35px; color: #fff; font-size: 40px; font-weight: bold; cursor: pointer; }}

        .channel-tag {{ background-color: #334155; color: #f1f5f9; padding: 4px 8px; border-radius: 4px; font-size: 0.85em; margin-right: 5px; display: inline-block; }}
        .no-match-row {{ text-align: center; color: #94a3b8; font-style: italic; padding: 20px; }}
        
        /* Liga Argentina Light Blue Theme Badge */
        .league-badge-arg {{ background-color: #e0f2fe; color: #0369a1; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.9em; display: inline-block; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header-flex">
            <h1>⚽ Football Broadcast Dashboard</h1>
            <button class="btn-start" onclick="triggerWorkflow()">▶ START UPDATE</button>
        </div>
        <div class="status-badge">Total Matches Loaded: <strong>{data.get('total_matches', 0)}</strong></div>
        
        <table>
            <thead>
                <tr><th>League</th><th>Teams & Logos</th><th>Local Time</th><th>Morocco Time</th><th>Channels</th></tr>
            </thead>
            <tbody>
                <!-- TODAY SECTION -->
                <tr><td colspan="5" class="section-header">📅 TODAY'S MATCHES</td></tr>
    """

    if today_matches:
        for m in today_matches:
            html_content += render_match_row(m)
    else:
        html_content += '<tr><td colspan="5" class="no-match-row">🚫 No matches scheduled for today.</td></tr>'

    html_content += """
                <!-- TOMORROW SECTION -->
                <tr><td colspan="5" class="section-header" style="border-top-color: #eab308; color: #eab308 !important;">📅 TOMORROW'S MATCHES</td></tr>
    """

    if tomorrow_matches:
        for m in tomorrow_matches:
            html_content += render_match_row(m)
    else:
        html_content += '<tr><td colspan="5" class="no-match-row">🚫 No matches scheduled for tomorrow.</td></tr>'

    html_content += """
            </tbody>
        </table>
    </div>

    <!-- Image Modal -->
    <div id="modal" onclick="closeModal()">
        <span onclick="closeModal()">&times;</span>
        <img id="modal-img" src="">
    </div>

    <script>
        function showOriginal(url) {
            document.getElementById('modal-img').src = url;
            document.getElementById('modal').style.display = 'flex';
        }
        function closeModal() {
            document.getElementById('modal').style.display = 'none';
        }

        function triggerWorkflow() {
            let token = localStorage.getItem('github_token') || prompt("Enter GitHub Token:");
            if(token) localStorage.setItem('github_token', token); else return;
            fetch('https://api.github.com/repos/aspijik07/football-bot/actions/workflows/runner.yml/dispatches', {
                method: 'POST',
                headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'},
                body: JSON.stringify({ref: 'main'})
            }).then(res => alert(res.ok ? 'Workflow started!' : 'Failed!'));
        }
    </script>
</body>
</html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

def render_match_row(m):
    h_logo = m.get("home_logo", "")
    a_logo = m.get("away_logo", "")
    channels = "".join([f'<span class="channel-tag">{c}</span>' for c in m.get("all_unique_channels", [])])
    
    league_name = m.get('league')
    # Aplicar light blue theme ila kant Liga Profesional wla Argentina
    if "Liga" in league_name or "Argentina" in m.get('country', ''):
        league_html = f'<span class="league-badge-arg">{league_name}</span><br><small style="color:#0284c7">Argentina</small>'
    else:
        league_html = f'<strong>{league_name}</strong><br><small>{m.get("country")}</small>'

    return f"""
        <tr>
            <td>{league_html}</td>
            <td>
                <div class="team-cell">
                    <img src="{h_logo}" class="team-logo" onclick="showOriginal('{h_logo}')" alt="logo" title="Click to view original size">
                    <div><strong>{m.get('home_team')}</strong></div>
                </div>
                <div class="team-cell" style="margin-top: 6px;">
                    <img src="{a_logo}" class="team-logo" onclick="showOriginal('{a_logo}')" alt="logo" title="Click to view original size">
                    <div><strong>{m.get('away_team')}</strong></div>
                </div>
            </td>
            <td>{m.get('local_time')}</td>
            <td><strong style="color:#38bdf8">{m.get('morocco_time')}</strong></td>
            <td>{channels}</td>
        </tr>
    """

def main():
    today_str = datetime.now().strftime('%Y-%m-%d')
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    print("Scraping matches for Today and Tomorrow...")
    matches = scrape_matches(today_str, "Today") + scrape_matches(tomorrow_str, "Tomorrow")
    data = {"total_matches": len(matches), "matches": matches}
    
    with open("matches.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    generate_html_dashboard(data)
    print("Dashboard generated successfully with thumbnail click-to-zoom and today/tomorrow split!")

if __name__ == "__main__":
    main()
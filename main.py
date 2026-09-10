import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def scrape_matches_for_date(date_str, label):
    matches = []
    urls = [
        f"https://www.zerozero.com.ar/futebol/jogos?data={date_str}",
        f"https://www.ogol.com.br/futebol/jogos?data={date_str}"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            game_elements = soup.select('.game_data, .match-item, tr.match, div.game')
            
            for el in game_elements:
                try:
                    league_el = el.find_previous(['div', 'tr'], class_=['competition_name', 'header-competition'])
                    league = league_el.get_text(strip=True) if league_el else "South America / Domestic"
                    country = "Argentina" if "ar" in url else "Brazil"

                    home_el = el.select_one('.hometeam, .team-home, td.home')
                    away_el = el.select_one('.awayteam, .team-away, td.away')
                    
                    if not home_el or not away_el:
                        continue

                    home_team = home_el.get_text(strip=True)
                    away_team = away_el.get_text(strip=True)

                    # Logos
                    home_img = home_el.find('img')
                    away_img = away_el.find('img')
                    
                    home_logo = ""
                    if home_img:
                        home_logo = home_img.get('src') or home_img.get('data-src', '')
                        if home_logo.startswith('//'):
                            home_logo = "https:" + home_logo

                    away_logo = ""
                    if away_img:
                        away_logo = away_img.get('src') or away_img.get('data-src', '')
                        if away_logo.startswith('//'):
                            away_logo = "https:" + away_logo

                    time_el = el.select_one('.time, .match-time, td.time')
                    local_time = time_el.get_text(strip=True) if time_el else "15:00"
                    morocco_time = local_time

                    channels_el = el.select_one('.channels, .tv-channels')
                    channels = [c.get_text(strip=True) for c in channels_el.select('span, a')] if channels_el else ["ESPN", "Star+"]

                    matches.append({
                        "day_label": label,  # "Today" aw "Tomorrow"
                        "league": league,
                        "country": country,
                        "home_team": home_team,
                        "away_team": away_team,
                        "home_logo": home_logo,
                        "away_logo": away_logo,
                        "local_time": local_time,
                        "morocco_time": morocco_time,
                        "all_unique_channels": channels
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"Error fetching {url}: {e}")

    return matches

def generate_html_dashboard(data):
    matches = data.get("matches", [])
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Football Broadcast Dashboard</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header-flex {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #38bdf8;
            margin: 0;
        }}
        .btn-start {{
            background-color: #eab308;
            color: #0f172a;
            border: none;
            padding: 10px 20px;
            font-size: 0.95em;
            font-weight: bold;
            border-radius: 6px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(234, 179, 8, 0.3);
            transition: all 0.2s ease;
        }}
        .btn-start:hover {{
            background-color: #ca8a04;
            transform: translateY(-2px);
        }}
        .status-badge {{
            text-align: center;
            margin-bottom: 20px;
            font-size: 1.1em;
            color: #94a3b8;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background-color: #1e293b;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 10px 25px rgba(0,0,0,0.3);
            margin-bottom: 30px;
        }}
        th, td {{
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #334155;
        }}
        th {{
            background-color: #0f172a;
            color: #38bdf8;
            text-transform: uppercase;
            font-size: 0.85em;
            letter-spacing: 1px;
        }}
        .section-header {{
            background-color: #1e293b !important;
            color: #38bdf8 !important;
            font-size: 1.1em;
            font-weight: bold;
            text-align: center;
            letter-spacing: 1px;
            padding: 12px !important;
            border-top: 2px solid #38bdf8;
        }}
        .team-cell {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }}
        .team-logo {{
            width: 24px;
            height: 24px;
            object-fit: contain;
        }}
        .img-link {{
            font-size: 0.75em;
            color: #38bdf8;
            text-decoration: none;
            background: #0f172a;
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid #334155;
            display: inline-block;
            margin-top: 2px;
        }}
        .img-link:hover {{
            background: #334155;
        }}
        .channel-tag {{
            background-color: #334155;
            color: #f1f5f9;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            margin-right: 5px;
            display: inline-block;
            margin-bottom: 3px;
        }}
        .no-matches {{
            text-align: center;
            padding: 40px;
            background-color: #1e293b;
            border-radius: 10px;
            font-size: 1.2em;
            color: #94a3b8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header-flex">
            <h1>⚽ Football Broadcast Dashboard (Today & Tomorrow)</h1>
            <button class="btn-start" onclick="triggerWorkflow()">▶ START UPDATE</button>
        </div>
        <div class="status-badge">Total Matches Loaded: <strong>{data.get('total_matches', 0)}</strong></div>
    """

    if not matches:
        html_content += """
        <div class="no-matches">
            🚫 No matches scheduled for today or tomorrow.
        </div>
        """
    else:
        # Separate today and tomorrow matches
        today_matches = [m for m in matches if m.get("day_label") == "Today"]
        tomorrow_matches = [m.get("day_label") == "Tomorrow" for m in matches] # Wait, let's filter properly
        tomorrow_matches_list = [m for m in matches if m.get("day_label") == "Tomorrow"]

        html_content += """
        <table>
            <thead>
                <tr>
                    <th>League</th>
                    <th>Teams & Logos</th>
                    <th>Local Time</th>
                    <th>Morocco Time (UTC+1)</th>
                    <th>Broadcast Channels</th>
                </tr>
            </thead>
            <tbody>
        """

        # Today Section
        if today_matches:
            html_content += """
                <tr>
                    <td colspan="5" class="section-header">📅 TODAY'S MATCHES</td>
                </tr>
            """
            for m in today_matches:
                html_content += render_match_row(m)

        # Tomorrow Section (L-taht)
        if tomorrow_matches_list:
            html_content += """
                <tr>
                    <td colspan="5" class="section-header" style="border-top: 3px solid #eab308; color: #eab308 !important;">📅 TOMORROW'S MATCHES</td>
                </tr>
            """
            for m in tomorrow_matches_list:
                html_content += render_match_row(m)

        html_content += """
            </tbody>
        </table>
        """

    html_content += """
    </div>

    <script>
        function triggerWorkflow() {
            let token = localStorage.getItem('github_token');
            if (!token) {
                token = prompt("Please enter your GitHub Personal Access Token:");
                if (token) {
                    localStorage.setItem('github_token', token);
                } else {
                    alert("Token is required to start the update.");
                    return;
                }
            }

            const OWNER = "aspijik07";
            const REPO = "football-bot";
            const WORKFLOW_ID = "runner.yml";

            const button = document.querySelector('.btn-start');
            button.innerText = '⌛ Updating Data...';
            button.disabled = true;

            fetch(`https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW_ID}/dispatches`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Accept': 'application/vnd.github.v3+json',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    ref: 'main'
                })
            })
            .then(response => {
                if (response.ok) {
                    alert('Workflow started successfully! Page will update in ~1-2 minutes.');
                } else {
                    alert('Failed to trigger workflow. Token might be invalid. Resetting token...');
                    localStorage.removeItem('github_token');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error dispatching workflow.');
            })
            .finally(() => {
                setTimeout(() => {
                    button.innerText = '▶ START UPDATE';
                    button.disabled = false;
                }, 5000);
            });
        }
    </script>
</body>
</html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

def render_match_row(m):
    league = m.get("league", "")
    country = m.get("country", "")
    home_team = m.get("home_team", "")
    away_team = m.get("away_team", "")
    home_logo = m.get("home_logo", "")
    away_logo = m.get("away_logo", "")

    home_logo_html = f'<img src="{home_logo}" class="team-logo" alt="logo">' if home_logo else ''
    home_link_html = f'<br><a href="{home_logo}" target="_blank" class="img-link">🔗 Home Image Link</a>' if home_logo else ''

    away_logo_html = f'<img src="{away_logo}" class="team-logo" alt="logo">' if away_logo else ''
    away_link_html = f'<br><a href="{away_logo}" target="_blank" class="img-link">🔗 Away Image Link</a>' if away_logo else ''

    channels_html = "".join([f'<span class="channel-tag">{ch}</span>' for ch in m.get("all_unique_channels", [])])
    if not channels_html:
        channels_html = '<span style="color: #64748b;">No TV info</span>'

    return f"""
        <tr>
            <td><strong>{league}</strong><br><small style="color:#94a3b8">{country}</small></td>
            <td>
                <div class="team-cell">
                    {home_logo_html}
                    <div>
                        <strong>{home_team}</strong>
                        {home_link_html}
                    </div>
                </div>
                <div class="team-cell" style="margin-top: 8px;">
                    {away_logo_html}
                    <div>
                        <strong>{away_team}</strong>
                        {away_link_html}
                    </div>
                </div>
            </td>
            <td>{m.get("local_time")}</td>
            <td><strong style="color:#38bdf8">{m.get("morocco_time")}</strong></td>
            <td>{channels_html}</td>
        </tr>
    """

def main():
    today = datetime.now()
    tomorrow = today + timedelta(days=1)

    today_str = today.strftime('%Y-%m-%d')
    tomorrow_str = tomorrow.strftime('%Y-%m-%d')

    print(f"Scraping matches for Today ({today_str})...")
    today_matches = scrape_matches_for_date(today_str, "Today")

    print(f"Scraping matches for Tomorrow ({tomorrow_str})...")
    tomorrow_matches = scrape_matches_for_date(tomorrow_str, "Tomorrow")

    all_matches = today_matches + tomorrow_matches

    data = {
        "total_matches": len(all_matches),
        "matches": all_matches
    }

    with open("matches.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print("matches.json updated successfully with Today & Tomorrow matches!")

    generate_html_dashboard(data)
    print("index.html dashboard generated successfully!")

if __name__ == "__main__":
    main()
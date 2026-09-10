import os
import json
import time
from datetime import datetime, timedelta
import requests

# ---------------------------------------------------------------------------
# 1. FLASHSCORE API / SCRAPER LOGIC
# ---------------------------------------------------------------------------
def fetch_flashscore_matches():
    """
    Fetches match data directly from Flashscore endpoints.
    Targets Brazil, Argentina, Copa Libertadores, and Copa Sudamericana.
    """
    matches = []
    
    # Headers to mimic real browser requests to Flashscore API
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Fsign": "SW90ZW50aWZpY2F0aW9u",
        "Referer": "https://www.flashscore.com/"
    }

    # Custom mapping for target leagues
    TARGET_LEAGUES = {
        "Série A": {"country": "Brazil", "type": "brazil"},
        "Copa do Brasil": {"country": "Brazil", "type": "brazil"},
        "Paulista": {"country": "Brazil", "type": "brazil"},
        "Liga Profesional": {"country": "Argentina", "type": "argentina"},
        "Copa Argentina": {"country": "Argentina", "type": "argentina"},
        "Copa Libertadores": {"country": "South America", "type": "libertadores"},
        "Copa Sudamericana": {"country": "South America", "type": "sudamericana"}
    }

    # Fetching Today (0) and Tomorrow (1) from Flashscore feed
    for day_offset in [0, 1]:
        day_label = "today" if day_offset == 0 else "tomorrow"
        url = f"https://local-global.flashscore.ninja/2/x/feed/f_1_{day_offset}_3_en_1"
        
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200:
                continue

            # Parsing Flashscore custom text format (delimited by ~SA÷)
            raw_data = res.text
            blocks = raw_data.split('~ZA÷')
            
            for block in blocks[1:]:
                lines = block.split('~')
                league_name = ""
                country_name = ""
                
                for line in lines:
                    if line.startswith('ZE÷'):
                        league_name = line.split('÷')[1]
                    elif line.startswith('ZB÷'):
                        country_name = line.split('÷')[1]

                # Match filtering against target leagues
                matched_target = None
                for target_key, meta in TARGET_LEAGUES.items():
                    if target_key.lower() in league_name.lower():
                        matched_target = meta
                        break

                if not matched_target:
                    continue

                # Parse individual match items
                match_items = block.split('~AA÷')
                for match_item in match_items[1:]:
                    m_data = {}
                    fields = match_item.split('~')
                    match_id = fields[0].split('÷')[0] if fields else ""
                    
                    home_team, away_team, start_time = "", "", ""
                    for field in fields:
                        if field.startswith('CX÷'):
                            home_team = field.split('÷')[1]
                        elif field.startswith('AF÷'):
                            away_team = field.split('÷')[1]
                        elif field.startswith('AD÷'):
                            timestamp = int(field.split('÷')[1])
                            dt = datetime.fromtimestamp(timestamp)
                            start_time = dt.strftime('%H:%M')

                    if home_team and away_team:
                        # Construct Flashscore match banner URL
                        banner_url = f"https://www.flashscore.com/res/image/featured-match/{match_id}.jpg"
                        
                        matches.append({
                            "day": day_label,
                            "league": league_name,
                            "country": matched_target["country"],
                            "type": matched_target["type"],
                            "home_team": home_team,
                            "away_team": away_team,
                            "local_time": f"{start_time} (Local)",
                            "morocco_time": start_time,
                            "banner_url": banner_url,
                            "channels": ["Flashscore Live"]
                        })
        except Exception as e:
            print(f"Flashscore parsing error for day {day_offset}: {e}")

    return matches


# ---------------------------------------------------------------------------
# 2. HTML GENERATOR (KHALFIYYAT L-ALWAN & UI DESIGN)
# ---------------------------------------------------------------------------
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
        
        /* --- KHALFIYYAT L-ROW (BACKGROUND COLORS) --- */
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
            <h1>⚽ Football Broadcast Dashboard (Flashscore)</h1>
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
        return '<tr><td colspan="5" class="no-matches">🚫 No matches scheduled on Flashscore for this day.</td></tr>'
    
    html = ""
    for m in matches:
        m_type = m.get("type", "")
        
        row_class = ""
        badge_class = "badge-other"

        if m_type == "libertadores":
            row_class = 'class="row-libertadores"'
            badge_class = 'badge-libertadores'
        elif m_type == "sudamericana":
            row_class = 'class="row-sudamericana"'
            badge_class = 'badge-sudamericana'
        elif m_type == "brazil":
            row_class = 'class="row-brazil"'
            badge_class = 'badge-brazil'
        elif m_type == "argentina":
            row_class = 'class="row-argentina"'
            badge_class = 'badge-arg'

        channels = "".join([f'<span class="channel-tag">{c}</span>' for c in m.get("channels", [])])
        banner_url = m.get("banner_url", "")

        html += f"""
        <tr {row_class}>
            <td>
                <span class="{badge_class}">{m['league']}</span><br>
                <small style="color: #cbd5e1; font-size: 0.8em;">{m['country']}</small>
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

# ---------------------------------------------------------------------------
# 3. MAIN EXECUTION
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Fetching matches exclusively from Flashscore...")
    matches = fetch_flashscore_matches()
    print(f"Total Flashscore matches found: {len(matches)}")
    
    output_html = generate_html_dashboard(matches)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(output_html)
    print("index.html successfully updated!")
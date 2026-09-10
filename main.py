import json
import re
from datetime import datetime, timedelta

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
        tr.brazil {{
            background-color: rgba(34, 197, 94, 0.15) !important;
            border-left: 5px solid #22c55e;
        }}
        tr.argentina {{
            background-color: rgba(56, 189, 248, 0.15) !important;
            border-left: 5px solid #38bdf8;
        }}
        tr.libertadores {{
            background-color: rgba(234, 179, 8, 0.15) !important;
            border-left: 5px solid #eab308;
        }}
        tr.sudamericana {{
            background-color: rgba(168, 85, 247, 0.15) !important;
            border-left: 5px solid #a855f7;
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
            <h1>⚽ Football Broadcast Dashboard</h1>
            <button class="btn-start" onclick="triggerWorkflow()">▶ START UPDATE</button>
        </div>
        <div class="status-badge">Total Matches Today: <strong>{data.get('total_matches', 0)}</strong></div>
    """

    if not matches:
        html_content += """
        <div class="no-matches">
            🚫 No matches scheduled today for the targeted leagues.
        </div>
        """
    else:
        html_content += """
        <table>
            <thead>
                <tr>
                    <th>League</th>
                    <th>Teams</th>
                    <th>Local Time</th>
                    <th>Morocco Time (UTC+1)</th>
                    <th>Broadcast Channels</th>
                </tr>
            </thead>
            <tbody>
        """
        for m in matches:
            league = m.get("league", "")
            country = m.get("country", "")
            
            row_class = ""
            if "Libertadores" in league:
                row_class = "libertadores"
            elif "Sudamericana" in league:
                row_class = "sudamericana"
            elif "Argentina" in country or "Argentina" in league:
                row_class = "argentina"
            elif "Brazil" in country or "Serie A" in league or "Brasileirao" in league:
                row_class = "brazil"

            channels_html = "".join([f'<span class="channel-tag">{ch}</span>' for ch in m.get("all_unique_channels", [])])
            if not channels_html:
                channels_html = '<span style="color: #64748b;">No TV info</span>'

            html_content += f"""
                <tr class="{row_class}">
                    <td><strong>{league}</strong><br><small style="color:#94a3b8">{country}</small></td>
                    <td><strong>{m.get("home_team")}</strong> vs <strong>{m.get("away_team")}</strong></td>
                    <td>{m.get("local_time")}</td>
                    <td><strong style="color:#38bdf8">{m.get("morocco_time")}</strong></td>
                    <td>{channels_html}</td>
                </tr>
            """

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
    print("Generated index.html dashboard with Start button successfully!")

def main():
    try:
        with open("matches.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading matches.json: {e}")
        data = {"matches": [], "total_matches": 0}

    generate_html_dashboard(data)

if __name__ == "__main__":
    main()
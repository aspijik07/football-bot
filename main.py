import os
import json
import requests
from datetime import datetime, timedelta, timezone

def convert_to_morocco_dt(utc_time_str):
    try:
        dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
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
    
    now_morocco = datetime.now(timezone(timedelta(hours=1)))
    time_diff_seconds = (match_dt - now_morocco).total_seconds()

    if time_diff_seconds <= 0:
        return "LIVE 🔴", "status-live"
    elif 0 < time_diff_seconds <= 3600:  # 9al mn sa3a
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

    now_morocco = datetime.now(timezone(timedelta(hours=1)))
    
    for day_offset in [0, 1]:
        day_label = "today" if day_offset == 0 else "tomorrow"
        target_date = now_morocco + timedelta(days=day_offset)
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
                            local_time = (match_dt - timedelta(hours=4)).strftime('%H:%M') if match_dt else "TBD"

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
                                "local_time": local_time,
                                "morocco_time": m_time,
                                "status_text": status_text,
                                "status_class": status_class,
                                "channels": ["TNT Sports", "ESPN Premium"],
                                "banner_url": f"https://images.fotmob.com/image_resources/logo/teamlogo/{home_id}.png" if home_id else "",
                            })
        except Exception as e:
            print(f"Fotmob error: {e}")

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
    now_morocco = datetime.now(timezone(timedelta(hours=1)))
    today_str = now_morocco.strftime('%d/%m/%Y')
    tomorrow_str = (now_morocco + timedelta(days=1)).strftime('%d/%m/%Y')

    today_m = [m for m in matches_data if m["day"] == "today"]
    tomorrow_m = [m for m in matches_data if m["day"] == "tomorrow"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Football Broadcast Dashboard</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; background: #0b1329; color: #fff; padding: 20px; }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; background: #151e32; border-radius: 8px; overflow: hidden; }}
        th, td {{ padding: 14px 12px; text-align: left; border-bottom: 1px solid #222f47; vertical-align: middle; }}
        th {{ background: #0b1329; color: #94a3b8; font-size: 0.75em; letter-spacing: 0.05em; text-transform: uppercase; }}
        .section-hdr {{ background: #1a243a; color: #eab308; font-weight: bold; text-align: center; font-size: 0.9em; }}
        
        /* Badges League Colors */
        .badge {{ padding: 4px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8em; display: inline-block; text-decoration: none; }}
        .badge-argentina {{ background: #7dd3fc; color: #0284c7; }}     /* Light Blue */
        .badge-brazil {{ background: #334155; color: #cbd5e1; }}        /* Dark Slate */
        .badge-libertadores {{ background: #fef08a; color: #a16207; }}  /* Yellow */
        .badge-sudamericana {{ background: #e9d5ff; color: #7e22ce; }}   /* Purple */
        .badge-default {{ background: #334155; color: #cbd5e1; }}

        /* Status Colors */
        .status-badge {{ padding: 3px 8px; border-radius: 12px; font-weight: bold; font-size: 0.75em; display: inline-block; text-transform: uppercase; }}
        .status-live {{ background: #ef4444; color: #fff; animation: pulse 1.5s infinite; }}
        .status-soon {{ background: #f97316; color: #fff; }}
        .status-finished {{ background: #22c55e; color: #fff; }}
        .status-scheduled {{ background: #3b82f6; color: #fff; }}
        .status-cancelled {{ background: #64748b; color: #fff; }}

        @keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} 100% {{ opacity: 1; }} }}

        .btn-update {{ background: #eab308; color: #000; border: none; padding: 10px 18px; font-weight: bold; border-radius: 6px; cursor: pointer; }}
        .btn-banner {{ background: #0284c7; color: #fff; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; margin-top: 6px; font-size: 0.8em; font-weight: 500; }}
        .channel-tag {{ background: #1e293b; color: #94a3b8; padding: 3px 6px; border-radius: 4px; font-size: 0.75em; margin-right: 4px; border: 1px solid #334155; inline-block; }}
        
        #modal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.85); justify-content: center; align-items: center; z-index: 1000; }}
        #modal img {{ max-width: 80%; max-height: 80%; border-radius: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin:0; font-size: 1.5em;">⚽ Football Broadcast Dashboard</h1>
            <button class="btn-update" onclick="triggerWorkflow()">▶ START UPDATE</button>
        </div>
        <table>
            <thead>
                <tr>
                    <th style="width: 20%;">LEAGUE</th>
                    <th style="width: 28%;">MATCH & BANNER</th>
                    <th style="width: 15%;">LOCAL TIME</th>
                    <th style="width: 15%;">MOROCCO TIME (GMT+1)</th>
                    <th style="width: 10%;">STATUS</th>
                    <th style="width: 12%;">CHANNELS</th>
                </tr>
            </thead>
            <tbody>
                <tr><td colspan="6" class="section-hdr">📅 TODAY'S MATCHES — {today_str} ({len(today_m)})</td></tr>
                {render_rows(today_m)}
                <tr><td colspan="6" class="section-hdr">📅 TOMORROW'S MATCHES — {tomorrow_str} ({len(tomorrow_m)})</td></tr>
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
        return '<tr><td colspan="6" style="text-align:center; color:#64748b; padding:15px;">🚫 No matches scheduled for these leagues today.</td></tr>'
    html = ""
    for m in matches:
        badge_class = get_league_color(m['league'], m['country'])
        banner_btn = f"<br><button class='btn-banner' onclick=\"showBanner('{m['banner_url']}')\">🖼️ View Match Banner</button>" if m['banner_url'] else ""
        channels_html = "".join([f"<span class='channel-tag'>{c}</span>" for c in m.get('channels', [])])
        
        html += f"""
        <tr>
            <td><span class="badge {badge_class}">{m['league']}</span><br><small style="color:#64748b">{m['country']}</small></td>
            <td><strong>{m['home_team']} <span style="color:#eab308">VS</span> {m['away_team']}</strong>{banner_btn}</td>
            <td style="color:#cbd5e1">{m['local_time']} (GMT-3)</td>
            <td><strong style="color:#38bdf8; font-size:1.05em">{m['morocco_time']}</strong></td>
            <td><span class="status-badge {m['status_class']}">{m['status_text']}</span></td>
            <td>{channels_html}</td>
        </tr>"""
    return html

if __name__ == "__main__":
    data = fetch_all_matches()
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(generate_html(data))
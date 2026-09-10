import os
import json
import time
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

def fetch_site_text(url, timeout=12):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=timeout)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            return soup.get_text(separator=' ', strip=True)[:25000]
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
    return ""

def generate_html_dashboard(data):
    matches = data.get("matches", [])
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Football Matches Dashboard</title>
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
        h1 {{
            text-align: center;
            color: #38bdf8;
            margin-bottom: 25px;
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
        /* Dynamic Row Colors based on League/Country */
        tr.brazil {{
            background-color: rgba(34, 197, 94, 0.15) !important; /* Soft Green */
            border-left: 5px solid #22c55e;
        }}
        tr.argentina {{
            background-color: rgba(56, 189, 248, 0.15) !important; /* Soft Blue */
            border-left: 5px solid #38bdf8;
        }}
        tr.libertadores {{
            background-color: rgba(234, 179, 8, 0.15) !important; /* Soft Gold */
            border-left: 5px solid #eab308;
        }}
        tr.sudamericana {{
            background-color: rgba(168, 85, 247, 0.15) !important; /* Soft Purple */
            border-left: 5px solid #a855f7;
        }}
        .badge {{
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 0.8em;
            font-weight: bold;
            display: inline-block;
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
        <h1>⚽ Football Broadcast Dashboard</h1>
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
            
            # Determine Color CSS Class
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
</body>
</html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Generated index.html dashboard successfully!")

def get_matches():
    sources = {
        "promiedos": "https://www.promiedos.com.ar/",
        "flashscore": "https://www.flashscore.com/",
        "ogol": "https://www.ogol.com.br/jogos_dia.php",
        "guiadetv": "https://www.guiadetv.com/",
        "futebolnatv": "https://www.futebolnatv.com.br/"
    }

    scraped_texts = {site: fetch_site_text(url) for site, url in sources.items()}

    allowed_leagues = [
        "Liga Profesional",
        "Copa Argentina",
        "Copa Libertadores",
        "Copa Sudamericana",
        "Serie A Betano",
        "Brasileirao"
    ]

    prompt = f"""
    You are a professional football broadcast data aggregator.
    Analyze the raw text from the 5 sources below for TODAY'S matches.

    TARGET LEAGUES ONLY:
    {json.dumps(allowed_leagues)}

    RAW DATA SOURCES:
    - PROMIEDOS: {scraped_texts['promiedos']}
    - FLASHSCORE: {scraped_texts['flashscore']}
    - OGOL: {scraped_texts['ogol']}
    - GUIADETV: {scraped_texts['guiadetv']}
    - FUTEBOLNATV: {scraped_texts['futebolnatv']}

    INSTRUCTIONS:
    1. Filter strictly for matches in the target leagues.
    2. Extract TV/Streaming channels found in EACH source individually.
    3. TIME & COUNTRY HANDLING:
       - "country": Host country/region ("Argentina", "Brazil", or "South America").
       - "local_time": Local time (UTC-3), e.g., "21:30 (UTC-3)".
       - "morocco_time": Calculated Morocco time (UTC+1), strictly +4 hours ahead of UTC-3 local time.
    4. IF NO MATCHES exist today, return an EMPTY array [].

    Return ONLY a valid JSON array of match objects formatted strictly like this:
    [
      {{
        "league": "Match League Name",
        "country": "Argentina",
        "home_team": "Home Team",
        "away_team": "Away Team",
        "local_time": "21:30 (UTC-3)",
        "morocco_time": "01:30 (UTC+1)",
        "source_channels": {{
          "promiedos": ["ESPN"],
          "guiadetv": ["SporTV"],
          "futebolnatv": ["DISNEY+"],
          "ogol": [],
          "flashscore": []
        }},
        "all_unique_channels": ["ESPN", "SporTV", "DISNEY+"],
        "matching_sources": ["promiedos", "guiadetv", "futebolnatv"]
      }}
    ]
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing!")

    client = genai.Client(api_key=api_key)

    max_retries = 4
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Calling Gemini AI (Attempt {attempt}/{max_retries})...")
            result = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            matches_data = json.loads(result.text.strip())
            
            if not matches_data or len(matches_data) == 0:
                final_output = {
                    "status": "No matches today",
                    "message": "There are no matches scheduled today for the targeted leagues.",
                    "total_matches": 0,
                    "matches": []
                }
            else:
                final_output = {
                    "status": "Success",
                    "total_matches": len(matches_data),
                    "matches": matches_data
                }
            
            with open("matches.json", "w", encoding="utf-8") as f:
                json.dump(final_output, f, ensure_ascii=False, indent=2)
            
            # Generate the visual HTML dashboard
            generate_html_dashboard(final_output)
            return

        except Exception as e:
            print(f"Attempt {attempt} failed with error: {e}")
            if attempt < max_retries:
                time.sleep(attempt * 5)
            else:
                error_output = {
                    "status": "Error",
                    "message": str(e),
                    "matches": []
                }
                with open("matches.json", "w", encoding="utf-8") as f:
                    json.dump(error_output, f, ensure_ascii=False, indent=2)
                generate_html_dashboard(error_output)
                raise e

if __name__ == "__main__":
    get_matches()
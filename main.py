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
        print(f"Fetching: {url}")
        res = requests.get(url, headers=headers, timeout=timeout)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # Strip tags and retrieve clean text snippet
            return soup.get_text(separator=' ', strip=True)[:25000]
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
    return ""

def get_matches():
    # Source URLs
    sources = {
        "promiedos": "https://www.promiedos.com.ar/",
        "flashscore": "https://www.flashscore.com/",
        "ogol": "https://www.ogol.com.br/jogos_dia.php",
        "guiadetv": "https://www.guiadetv.com/",
        "futebolnatv": "https://www.futebolnatv.com.br/"
    }

    scraped_texts = {}
    for site, url in sources.items():
        scraped_texts[site] = fetch_site_text(url)

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

    INSTRUCTIONS & CROSS-COMPARISON:
    1. Filter strictly for matches in the target leagues.
    2. Extract TV/Streaming channels found in EACH source individually for every match.
    3. Consolidate and deduplicate channels into a combined unified list (`all_unique_channels`).
    4. Provide a breakdown table of which source provided which channels.

    Return ONLY a valid JSON array of match objects formatted strictly like this:
    [
      {{
        "league": "Match League Name",
        "home_team": "Home Team",
        "away_team": "Away Team",
        "time": "Match Time",
        "source_channels": {{
          "promiedos": ["ESPN", "TNT Sports"],
          "guiadetv": ["SporTV", "Premiere"],
          "futebolnatv": ["Premiere"],
          "ogol": [],
          "flashscore": []
        }},
        "all_unique_channels": ["ESPN", "TNT Sports", "SporTV", "Premiere"],
        "matching_sources": ["promiedos", "guiadetv", "futebolnatv"]
      }}
    ]
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing!")

    client = genai.Client(api_key=api_key)

    try:
        print("Calling Gemini AI to parse and compare sources...")
        result = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        matches_data = json.loads(result.text.strip())
        
        with open("matches.json", "w", encoding="utf-8") as f:
            json.dump(matches_data, f, ensure_ascii=False, indent=2)
        
        print(f"Successfully processed {len(matches_data)} matches from all sites into matches.json!")

    except Exception as e:
        print(f"Execution failed: {e}")
        raise e

if __name__ == "__main__":
    get_matches()
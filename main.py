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
            return soup.get_text(separator=' ', strip=True)[:25000]
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
    return ""

def get_matches():
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

    INSTRUCTIONS:
    1. Filter strictly for matches in the target leagues.
    2. Extract TV/Streaming channels found in EACH source individually for every match.
    3. Consolidate and deduplicate channels into `all_unique_channels`.
    4. IF NO MATCHES exist today for these specific leagues, return an EMPTY array [].

    Return ONLY a valid JSON array of match objects formatted like this:
    [
      {{
        "league": "Match League Name",
        "home_team": "Home Team",
        "away_team": "Away Team",
        "time": "Match Time",
        "source_channels": {{
          "promiedos": ["ESPN"],
          "guiadetv": ["SporTV"],
          "futebolnatv": ["Premiere"],
          "ogol": [],
          "flashscore": []
        }},
        "all_unique_channels": ["ESPN", "SporTV", "Premiere"],
        "matching_sources": ["promiedos", "guiadetv", "futebolnatv"]
      }}
    ]
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing!")

    client = genai.Client(api_key=api_key)

    # Robust Retry Loop for API 503 / High Demand errors
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
                print("No matches found today for specified leagues.")
            else:
                final_output = {
                    "status": "Success",
                    "total_matches": len(matches_data),
                    "matches": matches_data
                }
                print(f"Successfully processed {len(matches_data)} matches!")
            
            with open("matches.json", "w", encoding="utf-8") as f:
                json.dump(final_output, f, ensure_ascii=False, indent=2)
            
            return  # Success, exit function!

        except Exception as e:
            print(f"Attempt {attempt} failed with error: {e}")
            if attempt < max_retries:
                wait_time = attempt * 5
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                # If all attempts fail, write clean error JSON instead of crashing workflow
                error_output = {
                    "status": "Error",
                    "message": f"Server unavailable after {max_retries} retries: {str(e)}",
                    "matches": []
                }
                with open("matches.json", "w", encoding="utf-8") as f:
                    json.dump(error_output, f, ensure_ascii=False, indent=2)
                raise e

if __name__ == "__main__":
    get_matches()
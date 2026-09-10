import os
import json
import time
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

def fetch_site_text(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            return soup.get_text(separator=' ', strip=True)[:30000]
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return ""

def get_matches():
    print("Fetching data from Promiedos & Flashscore...")
    promiedos_text = fetch_site_text("https://www.promiedos.com.ar/")
    flashscore_text = fetch_site_text("https://www.flashscore.com/")

    # Target leagues list - modify or append new leagues here
    allowed_leagues = [
        "Argentina : Liga Profesional",
        "ARGENTINA : Copa Argentina",
        "SOUTH AMERICA: Copa Libertadores",
        "SOUTH AMERICA: Copa Sudamericana",
        "BRAZIL: Serie A Betano"
    ]

    prompt = f"""
    You are an expert football data extractor.
    Extract today's matches ONLY for the following leagues/tournaments:
    {json.dumps(allowed_leagues, indent=2)}

    RULES:
    1. STRICT FILTERING: Do NOT extract matches from any other league or friendly games outside these exact leagues.
    2. Extract the TV channels/broadcasting networks for each match whenever available (especially from Promiedos text).

    RAW TEXT SOURCE 1 (Promiedos):
    {promiedos_text}

    RAW TEXT SOURCE 2 (Flashscore):
    {flashscore_text}

    Return ONLY a valid JSON array of objects with these exact keys:
    - "league": Name of the allowed league
    - "home_team": Home team name
    - "away_team": Away team name
    - "time": Match time or status
    - "channels": Array of strings representing TV channels broadcasting the match (empty array [] if not found)
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing!")

    client = genai.Client(api_key=api_key)

    try:
        print("Calling Gemini AI...")
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
        
        print(f"Successfully saved {len(matches_data)} targeted matches to matches.json!")

    except Exception as e:
        print(f"Execution failed: {e}")
        raise e

if __name__ == "__main__":
    get_matches()
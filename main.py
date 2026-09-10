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
            return soup.get_text(separator=' ', strip=True)[:25000]
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return ""

def get_matches():
    print("Fetching data from Promiedos & Flashscore...")
    promiedos_text = fetch_site_text("https://www.promiedos.com.ar/")
    flashscore_text = fetch_site_text("https://www.flashscore.com/")

    prompt = f"""
    You are an expert football data aggregator.
    Extract today's football matches using both sources provided.

    SOURCE 1 (Promiedos - Good for TV channels and South American / European leagues):
    {promiedos_text}

    SOURCE 2 (Flashscore - Good for Global matches and live scores):
    {flashscore_text}

    Return ONLY a valid JSON array of match objects with these exact keys:
    - "league": Name of tournament/league
    - "home_team": Home team name
    - "away_team": Away team name
    - "time": Match time or status
    - "channels": Array of TV channels (from Promiedos if available, else empty array [])
    - "source": String ("Promiedos", "Flashscore", or "Both")
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
        
        print(f"Successfully saved {len(matches_data)} matches to matches.json!")

    except Exception as e:
        print(f"Execution failed: {e}")
        raise e

if __name__ == "__main__":
    get_matches()
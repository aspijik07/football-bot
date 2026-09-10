import os
import json
import time
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

def get_matches():
    # 1. Fetch Promiedos TV page specifically
    url = "https://www.promiedos.com.ar/tv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print("Fetching TV schedule from Promiedos...")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to load Promiedos TV page. Status code: {response.status_code}")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    page_text = soup.get_text(separator=' ', strip=True)[:30000]

    # 2. Broader prompt to capture all available TV matches
    prompt = f"""
    Extract ALL football matches listed in the raw text along with their broadcast TV channels and leagues.
    
    Return a pure JSON array of objects with these exact keys:
    - "league": Tournament or league name
    - "home_team": Home team
    - "away_team": Away team
    - "time": Match time or status
    - "channels": Array of TV channel names broadcasting the match (e.g. ["ESPN", "TNT Sports"])

    Source text:
    {page_text}
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing!")

    client = genai.Client(api_key=api_key)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Sending request to Gemini AI (Attempt {attempt + 1}/{max_retries})...")
            result = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            cleaned_response = result.text.strip().replace("```json", "").replace("```", "")
            matches_data = json.loads(cleaned_response)
            
            with open("matches.json", "w", encoding="utf-8") as f:
                json.dump(matches_data, f, ensure_ascii=False, indent=2)
            
            print(f"Successfully extracted {len(matches_data)} matches to matches.json!")
            return

        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise e

if __name__ == "__main__":
    get_matches()
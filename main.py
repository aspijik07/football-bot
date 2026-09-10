import os
import json
import time
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

def get_matches():
    url = "https://www.promiedos.com.ar/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print("Fetching matches from Promiedos...")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to load Promiedos page. Status code: {response.status_code}")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Clean up text extraction
    text_content = soup.get_text(separator='\n', strip=True)[:30000]

    prompt = f"""
    You are a data extraction assistant.
    Extract all football matches from the provided text.
    
    Return a valid JSON array of objects. Each object MUST have these exact keys:
    - "league": Name of the league/tournament
    - "home_team": Name of the home team
    - "away_team": Name of the away team
    - "time": Match time or status (e.g., "18:00", "Final", "30'")
    - "channels": List of TV channels showing the match (if any, otherwise empty array [])

    Raw text:
    {text_content}
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing in GitHub Secrets!")

    client = genai.Client(api_key=api_key)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Calling Gemini AI (Attempt {attempt + 1}/{max_retries})...")
            result = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            raw_text = result.text.strip()
            print("Raw AI Response:", raw_text[:300]) # Debug log
            
            matches_data = json.loads(raw_text)
            
            with open("matches.json", "w", encoding="utf-8") as f:
                json.dump(matches_data, f, ensure_ascii=False, indent=2)
            
            print(f"Saved {len(matches_data)} matches to matches.json successfully!")
            return

        except Exception as e:
            print(f"Attempt {attempt + 1} failed with error: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise e

if __name__ == "__main__":
    get_matches()
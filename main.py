import os
import json
import time
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

def get_matches():
    # 1. Fetch Promiedos page content
    url = "https://www.promiedos.com.ar/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print("Fetching data from Promiedos...")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to load Promiedos page. Status code: {response.status_code}")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    page_text = soup.get_text(separator=' ', strip=True)[:40000]  # Limit context size for fast processing

    # 2. Prompt for Gemini
    prompt = f"""
    Extract today's football matches from the following text (focusing on Argentine, Brazilian, or major Latin American / International leagues).
    For each match, return a JSON array of objects with these exact keys:
    - "league": Name of the league/tournament
    - "home_team": Name of the home team
    - "away_team": Name of the away team
    - "time": Match time or status (e.g. '18:00', 'Finalizado', 'En vivo')
    - "tv": Array of TV channels broadcasting the match (e.g. ["ESPN", "TNT Sports"])

    Only return VALID JSON raw text without any Markdown formatting or code block quotes (do not include ```json).

    Source text:
    {page_text}
    """

    # 3. Call Gemini API with retry logic for 503 / Server Overload errors
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
            
            # Save output to matches.json
            with open("matches.json", "w", encoding="utf-8") as f:
                json.dump(matches_data, f, ensure_ascii=False, indent=2)
            
            print("Successfully updated matches.json!")
            return

        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print("Waiting 5 seconds before retrying...")
                time.sleep(5)
            else:
                raise e

if __name__ == "__main__":
    get_matches()
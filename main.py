import os
import json
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# 1. Config Client b-SDK l-jdid
API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
client = genai.Client(api_key=API_KEY)

# 2. Scraper dyal Promiedos TV Guide
def get_raw_schedule():
    url = "https://www.promiedos.com.ar/tv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        text_data = soup.get_text(separator="\n", strip=True)
        return text_data[:8000]
    except Exception as e:
        print(f"Error scraping: {e}")
        return ""

# 3. Gemini Extraction b-Model Gemini 3.6 Flash
def extract_matches_with_ai(raw_text):
    prompt = f"""
    Extract all football matches, kick-off times, leagues, and official TV channels from this raw text.
    Focus on Argentina (Liga Profesional) and Brazil (Brasileirao) matches.
    Return ONLY a pure valid JSON array format like this:
    [
      {{
        "league": "Liga Profesional",
        "home_team": "Boca Juniors",
        "away_team": "River Plate",
        "time": "21:00",
        "channels": ["TNT Sports", "ESPN Premium"]
      }}
    ]

    Raw Text:
    {raw_text}
    """
    
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)

if __name__ == "__main__":
    print("Fetching schedule...")
    raw_data = get_raw_schedule()
    
    if raw_data:
        print("Extracting with Gemini AI...")
        structured_json = extract_matches_with_ai(raw_data)
        
        # Save output
        with open("matches.json", "w", encoding="utf-8") as f:
            json.dump(structured_json, f, ensure_ascii=False, indent=2)
            
        print("Done! Check matches.json file.")
    else:
        print("Failed to fetch schedule text.")
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("SERPAPI_API_KEY")

resp = requests.get(
    "https://serpapi.com/search",
    params={"engine": "google_lens", "url": "https://files.catbox.moe/w7ly5i.jpg", "api_key": api_key},
)
data = resp.json()
print(json.dumps(data.get("visual_matches", [])[:3], indent=2))

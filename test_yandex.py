import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("SERPAPI_API_KEY")

resp = requests.get(
    "https://serpapi.com/search",
    params={"engine": "yandex_images", "url": "https://files.catbox.moe/w7ly5i.jpg", "api_key": api_key},
)
print("Status:", resp.status_code)
print("Type of json:", type(resp.json()))
print("JSON snippet:", str(resp.json())[:200])

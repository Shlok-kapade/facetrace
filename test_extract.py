import requests
import re

def extract_profile_from_social_post(url):
    # Try twitter logic first (no need to fetch)
    if 'x.com' in url or 'twitter.com' in url:
        m = re.search(r'(x\.com|twitter\.com)/([^/]+)/status', url)
        if m:
            return f"https://x.com/{m.group(2)}"
            
    # Try tiktok logic first (no need to fetch)
    if 'tiktok.com' in url:
        m = re.search(r'tiktok\.com/(@[^/]+)/video', url)
        if m:
            return f"https://www.tiktok.com/{m.group(1)}"
            
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=5)
        # Search for og:url content
        m = re.search(r'property="og:url"\s+content="([^"]+)"', resp.text)
        if m:
            content = m.group(1)
            if 'instagram.com' in content:
                m2 = re.search(r'instagram\.com/([^/]+)/p/', content)
                if m2:
                    return f"https://www.instagram.com/{m2.group(1)}/"
    except Exception as e:
        print(e)
    return None

print(extract_profile_from_social_post('https://www.instagram.com/p/DQ6v3JHiIpk/'))
print(extract_profile_from_social_post('https://x.com/Chasemaster_VK/status/1996'))

import requests
import re
from typing import Tuple
from src.config import config

def _is_social_profile(url: str) -> bool:
    """Check if URL is a profile."""
    url_lower = url.lower()
    post_indicators = ["/status/", "/p/", "/reel/", "/stories/", "/posts/", "/photo", "/watch", "/shorts/", "/pulse/", "/events/", "/groups/", "/explore/"]
    if any(ind in url_lower for ind in post_indicators):
        return False
    return True

def _extract_profile_direct(url: str) -> str:
    """Attempt to extract the profile URL directly from the post URL or metadata."""
    if 'x.com' in url or 'twitter.com' in url:
        m = re.search(r'(x\.com|twitter\.com)/([^/]+)/status', url)
        if m:
            return f"https://x.com/{m.group(2)}"
            
    if 'tiktok.com' in url:
        m = re.search(r'tiktok\.com/(@[^/]+)/video', url)
        if m:
            return f"https://www.tiktok.com/{m.group(1)}"
            
    if 'instagram.com/p/' in url or 'instagram.com/reel/' in url:
        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=5)
            m = re.search(r'property="og:url"\s+content="([^"]+)"', resp.text)
            if m:
                content = m.group(1)
                m2 = re.search(r'instagram\.com/([^/]+)/(?:p|reel)/', content)
                if m2:
                    return f"https://www.instagram.com/{m2.group(1)}/"
        except Exception:
            pass
            
    return None

def resolve_profile(url: str, title: str) -> Tuple[str, str]:
    """
    Given a social media post URL and its search result title, try to find
    the actual user's profile URL. Returns (url, title).
    """
    if _is_social_profile(url):
        return url, title
        
    # Attempt direct deterministic extraction first
    direct_url = _extract_profile_direct(url)
    if direct_url:
        print(f"  [Resolver] Direct extraction: {url[:40]}... → {direct_url}")
        return direct_url, title
    
    # Use SerpApi to search the post title and find the associated profile
    if not config.SERPAPI_API_KEY:
        return url, title
        
    print(f"  [Resolver] Searching for profile matching post title...")
    # Clean the title heavily
    clean_title = title.split("|")[0].strip()
    clean_title = re.sub(r'\.\.\.$', '', clean_title).strip()
    
    # Add site restriction based on domain to narrow down to the creator's profile
    site = ""
    if "instagram.com" in url:
        site = "site:instagram.com"
    elif "x.com" in url or "twitter.com" in url:
        site = "site:x.com OR site:twitter.com"
    elif "youtube.com" in url:
        site = "site:youtube.com"
        
    q = f'"{clean_title}" {site}'.strip()
    try:
        resp = requests.get('https://serpapi.com/search', params={'engine': 'google', 'q': q, 'api_key': config.SERPAPI_API_KEY}, timeout=10)
        data = resp.json()
        for res in data.get('organic_results', []):
            link = res.get('link', '')
            if _is_social_profile(link) and any(d in link for d in ["instagram.com", "x.com", "twitter.com", "youtube.com"]):
                print(f"  [Resolver] Upgraded post to profile: {link}")
                return link, res.get('title', 'Profile')
    except Exception as e:
        print(f"  [Resolver] Failed to resolve profile: {e}")
        
    # Fallback
    return url, title

"""Multi-engine reverse image search via SerpApi.

Queries up to 3 search engines (Google Lens, Yandex Images, Google Reverse Image)
and merges/deduplicates results for maximum coverage.
"""

import requests
from dataclasses import dataclass, field
from typing import List
from urllib.parse import urlparse

from src.config import config


@dataclass
class RawMatch:
    """A single result from any search engine."""
    url: str
    title: str
    source: str = ""
    thumbnail: str = ""
    engine: str = ""  # Which engine found this


def _upload_image_temp(image_path: str) -> str:
    """Upload image to catbox.moe for a public URL."""
    print(f"  Uploading image to temporary host...")
    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": ("face.jpg", f, "image/jpeg")},
                timeout=30,
            )
        resp.raise_for_status()
        url = resp.text.strip()
        print(f"  Uploaded to: {url}")
        return url
    except requests.RequestException as e:
        raise RuntimeError(f"Could not upload image: {e}")


def _search_google_lens(image_url: str, api_key: str) -> List[RawMatch]:
    """Search using Google Lens engine."""
    print(f"    [Engine 1/3] Google Lens...")
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"engine": "google_lens", "url": image_url, "api_key": api_key},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"    [Engine 1/3] Google Lens FAILED: {e}")
        return []

    matches = []
    for m in data.get("visual_matches", []):
        link = m.get("link", "")
        if link:
            matches.append(RawMatch(
                url=link,
                title=m.get("title", "Unknown"),
                source=m.get("source", ""),
                thumbnail=m.get("thumbnail", ""),
                engine="google_lens",
            ))

    # Also check knowledge_graph
    kg = data.get("knowledge_graph", [])
    if isinstance(kg, list):
        for item in kg:
            link = item.get("link", "")
            if link:
                matches.append(RawMatch(
                    url=link,
                    title=item.get("title", "Unknown"),
                    source=item.get("source", ""),
                    engine="google_lens_kg",
                ))

    print(f"    [Engine 1/3] Google Lens: {len(matches)} result(s)")
    return matches


def _search_yandex(image_url: str, api_key: str) -> List[RawMatch]:
    """Search using Yandex Images reverse image search."""
    print(f"    [Engine 2/3] Yandex Images...")
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "yandex_images",
                "url": image_url,
                "api_key": api_key,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"    [Engine 2/3] Yandex FAILED: {e}")
        return []

    if not isinstance(data, dict):
        print(f"    [Engine 2/3] Yandex returned non-dict response")
        return []

    matches = []
    # Yandex returns results in "image_results"
    for m in data.get("image_results", []):
        if not isinstance(m, dict):
            continue
            
        src = m.get("source", {})
        if isinstance(src, str):
            src_name = src
            src_link = ""
            src_title = ""
        else:
            src_name = src.get("name", "")
            src_link = src.get("link", "")
            src_title = src.get("title", "")
            
        link = src_link or m.get("link", "")
        title = src_title or m.get("title", "Unknown")
        
        # Handle thumbnail which could be a dict or string
        thumb = m.get("thumbnail", "")
        if isinstance(thumb, dict):
            thumb = thumb.get("link", "") or thumb.get("url", "")
            
        if link:
            matches.append(RawMatch(
                url=link,
                title=title,
                source=src_name,
                thumbnail=thumb,
                engine="yandex",
            ))

    print(f"    [Engine 2/3] Yandex: {len(matches)} result(s)")
    return matches


def _search_google_reverse(image_url: str, api_key: str) -> List[RawMatch]:
    """Search using Google Reverse Image search."""
    print(f"    [Engine 3/3] Google Reverse Image...")
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google_reverse_image",
                "image_url": image_url,
                "api_key": api_key,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"    [Engine 3/3] Google Reverse FAILED: {e}")
        return []

    matches = []
    for m in data.get("image_results", []):
        link = m.get("link", "")
        if link:
            matches.append(RawMatch(
                url=link,
                title=m.get("title", "Unknown"),
                source=m.get("source", ""),
                thumbnail=m.get("thumbnail", ""),
                engine="google_reverse",
            ))

    # Also check inline_images
    for m in data.get("inline_images", []):
        link = m.get("source", "") or m.get("link", "")
        if link:
            matches.append(RawMatch(
                url=link,
                title=m.get("title", "Unknown"),
                source=m.get("source_name", ""),
                thumbnail=m.get("thumbnail", ""),
                engine="google_reverse",
            ))

    print(f"    [Engine 3/3] Google Reverse: {len(matches)} result(s)")
    return matches


def _deduplicate(matches: List[RawMatch]) -> List[RawMatch]:
    """Deduplicate matches by URL domain+path, keeping the first occurrence."""
    seen = set()
    unique = []
    for m in matches:
        parsed = urlparse(m.url)
        key = f"{parsed.netloc}{parsed.path}".lower().rstrip("/")
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


def multi_engine_search(
    image_path: str,
    image_url: str = None,
    engines: list = None,
) -> List[RawMatch]:
    """
    Run reverse image search across multiple engines and return merged results.

    Args:
        image_path: Path to local image file (will be uploaded if no image_url).
        image_url: Optional pre-existing public URL.
        engines: List of engine names to use. Defaults to config.SEARCH_ENGINES.

    Returns:
        Deduplicated list of RawMatch results from all engines.
    """
    if not config.SERPAPI_API_KEY:
        raise RuntimeError("SERPAPI_API_KEY not set in .env")

    if engines is None:
        engines = config.SEARCH_ENGINES
    # Get public URL
    if not image_url:
        image_url = _upload_image_temp(image_path)

    api_key = config.SERPAPI_API_KEY
    
    # Execute searches sequentially (could be parallelized)
    engine_map = {
        "google_lens": ("Google Lens", _search_google_lens),
        "yandex_images": ("Yandex Images", _search_yandex),
        "google_reverse_image": ("Google Reverse Image", _search_google_reverse),
    }

    requested_engines = engines or config.SEARCH_ENGINES
    all_matches = []
    
    for i, engine_key in enumerate(requested_engines, 1):
        if engine_key not in engine_map:
            continue
            
        name, func = engine_map[engine_key]
        print(f"    [Engine {i}/{len(requested_engines)}] {name}...")
        try:
            matches = func(image_url, api_key)
            # Limit each engine to top 30 results to reduce noise
            matches = matches[:30]
            print(f"    [Engine {i}/{len(requested_engines)}] {name.split()[0]}: {len(matches)} result(s)")
            all_matches.extend(matches)
        except Exception as e:
            print(f"    [Engine {i}/{len(requested_engines)}] {name} failed: {e}")

    # Deduplicate
    unique = _deduplicate(all_matches)
    print(f"  Total: {len(all_matches)} results → {len(unique)} unique after dedup")

    return unique

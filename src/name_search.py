"""Search for a person's social profiles by name and verify biometrically.

Strategy (in priority order):
  1. Knowledge Graph — SerpApi returns verified social profiles (Instagram,
     X, Facebook, etc.) directly from Google's knowledge panel. Best for
     public figures.
  2. Organic Results — For lesser-known people, Google organic search
     already surfaces their real profiles (e.g., "Sharon Verma" returns
     instagram.com/sharonverma). We grab these and verify.
  3. Profile Photo Verification — For every candidate profile, we search
     Google Images for photos of that profile and biometrically verify
     against the input face.
"""

import re
import requests
from typing import Optional, Tuple, List

from src.config import config
from src.face_verify import verify_face_from_url


# Domains we consider "social" profiles
SOCIAL_DOMAINS = [
    "instagram.com", "linkedin.com", "x.com", "twitter.com",
    "youtube.com", "facebook.com", "tiktok.com",
]


def _is_social_url(url: str) -> bool:
    """Check if URL belongs to a social platform."""
    return any(d in url.lower() for d in SOCIAL_DOMAINS)


def _is_profile_url(url: str) -> bool:
    """Check if URL looks like a profile page (not a post/reel/status)."""
    url_lower = url.lower()
    post_indicators = [
        "/status/", "/p/", "/reel/", "/stories/", "/posts/", "/photo",
        "/watch", "/shorts/", "/pulse/", "/events/", "/groups/", "/explore/",
        "/search", "/hashtag/", "/trending", "/playlist",
    ]
    return not any(ind in url_lower for ind in post_indicators)


def _search_google(query: str) -> dict:
    """Run a Google search via SerpApi, return full response."""
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google",
                "q": query,
                "num": 10,
                "api_key": config.SERPAPI_API_KEY,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"    [NameSearch] Google search failed: {e}")
        return {}


def _verify_profile_photo(
    profile_url: str,
    input_encoding: list,
    tolerance: float,
) -> Optional[Tuple[float, bool]]:
    """Search Google Images for a profile's photos and biometrically verify.

    Returns (distance, is_match) or None if no photos found.
    """
    # Extract username/identifier from URL
    username = profile_url.rstrip("/").split("/")[-1]
    if not username:
        return None

    # Determine platform for search context
    platform = ""
    for d in SOCIAL_DOMAINS:
        if d in profile_url:
            platform = d.split(".")[0]
            break

    query = f"{username} {platform}" if platform else username

    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google_images",
                "q": query,
                "num": 5,
                "api_key": config.SERPAPI_API_KEY,
            },
            timeout=15,
        )
        data = resp.json()

        best_dist = None
        for img in data.get("images_results", [])[:5]:
            thumb = img.get("thumbnail", "")
            if not thumb:
                continue
            result = verify_face_from_url(input_encoding, thumb, tolerance)
            if result.error:
                continue
            if best_dist is None or result.distance < best_dist:
                best_dist = result.distance
            if result.is_match:
                return (result.distance, True)

        if best_dist is not None:
            return (best_dist, False)
    except Exception:
        pass

    return None


def search_by_name_and_verify(
    candidate_names: List[str],
    input_encoding: list,
    tolerance: float = None,
) -> Optional[Tuple[str, str, float]]:
    """Search for social profiles by name and biometrically verify.

    Uses a multi-strategy approach:
      1. Google Knowledge Graph (verified profiles for public figures)
      2. Google Organic Results (social profile URLs)
      3. Biometric verification via Google Images

    Args:
        candidate_names: Person names to search for.
        input_encoding: 128-d face encoding to verify against.
        tolerance: Match tolerance (defaults to config).

    Returns:
        (profile_url, profile_title, distance) or None.
    """
    if tolerance is None:
        tolerance = config.FACE_MATCH_TOLERANCE

    if not candidate_names:
        return None

    # Use a slightly relaxed tolerance for name-based search since
    # profile photos may differ from the input image
    name_tolerance = tolerance

    print(f"  [NameSearch] Trying {len(candidate_names)} candidate name(s): {candidate_names}")

    for name in candidate_names:
        print(f"    [NameSearch] Searching for '{name}'...")
        data = _search_google(name)

        if not data:
            continue

        # ── Strategy 1: Knowledge Graph profiles ──
        kg = data.get("knowledge_graph", {})
        if kg:
            profiles = kg.get("profiles", [])
            if profiles:
                print(f"    [NameSearch] Found Knowledge Graph with {len(profiles)} profile(s)")
                for p in profiles:
                    purl = p.get("link", "")
                    pname = p.get("name", "")
                    if not purl:
                        continue

                    # Knowledge graph profiles are highly trusted — verify photo
                    check = _verify_profile_photo(purl, input_encoding, name_tolerance)
                    if check is not None:
                        dist, is_match = check
                        status = "✓" if is_match else "✗"
                        print(f"      {status} {pname}: {purl} (dist={dist:.4f})")
                        if is_match:
                            title = f"{kg.get('title', name)} (@{purl.rstrip('/').split('/')[-1]})"
                            return (purl, title, dist)
                    else:
                        # Can't get photo — trust knowledge graph for known entities
                        print(f"      ? {pname}: {purl} (no photo to verify, trusting KG)")
                        title = f"{kg.get('title', name)} (@{purl.rstrip('/').split('/')[-1]})"
                        return (purl, title, 0.0)

        # ── Strategy 2: Organic results — social profile URLs ──
        organic = data.get("organic_results", [])
        for result in organic:
            url = result.get("link", "")
            title = result.get("title", "")

            if not url or not _is_social_url(url) or not _is_profile_url(url):
                continue

            # Found a social profile URL — verify with photo
            photo_url = result.get("thumbnail", "")
            if photo_url:
                vr = verify_face_from_url(input_encoding, photo_url, name_tolerance)
                if not vr.error:
                    if vr.is_match:
                        print(f"      ✓ {title[:40]} | {url[:50]} (dist={vr.distance:.4f})")
                        return (url, title, vr.distance)
                    else:
                        print(f"      ✗ {title[:40]} | {url[:50]} (dist={vr.distance:.4f})")
                        continue

            # No SERP thumbnail or verification failed — try Google Images
            check = _verify_profile_photo(url, input_encoding, name_tolerance)
            if check is not None:
                dist, is_match = check
                status = "✓" if is_match else "✗"
                print(f"      {status} {title[:40]} | {url[:50]} (dist={dist:.4f})")
                if is_match:
                    return (url, title, dist)
            else:
                print(f"      - {title[:40]} | {url[:50]} (no photo)")

    return None

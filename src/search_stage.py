"""Stage 3: Profile resolution & ranking of multi-engine search results.

Two-pass strategy:
  Pass 1 – Thumbnail biometric verification (fast, works for famous people
           whose photos are widely indexed).
  Pass 2 – Name extraction fallback (for "unfamous" people).  Extract
           candidate names from result titles, search social platforms by
           name, and biometrically verify the profile photos.
"""

from dataclasses import dataclass, field
from typing import List

from src.config import config
from src.multi_search import multi_engine_search, RawMatch
from src.face_verify import verify_face_from_url


@dataclass
class SearchMatch:
    """A matched result after ranking and profile resolution."""
    url: str
    title: str
    source: str
    thumbnail: str = ""
    is_social: bool = False
    is_profile: bool = False
    engine: str = ""
    distance: float = 1.0


@dataclass
class SearchResult:
    """Result from the full multi-engine web search stage."""
    best_match: SearchMatch = None
    all_matches: List[SearchMatch] = field(default_factory=list)


def _is_social_domain(url: str) -> bool:
    url_lower = url.lower()
    return any(domain in url_lower for domain in config.SOCIAL_DOMAINS)


def _is_social_profile(url: str) -> bool:
    if not _is_social_domain(url):
        return False
    url_lower = url.lower()
    post_indicators = [
        "/status/", "/p/", "/reel/", "/stories/", "/posts/", "/photo", 
        "/watch", "/shorts/", "/pulse/", "/events/", "/groups/", "/explore/"
    ]
    if any(ind in url_lower for ind in post_indicators):
        return False
    return True


def search_and_verify(face_crop_path: str, input_encoding: list, image_url: str = None) -> SearchResult:
    """
    1. Multi-engine reverse image search.
    2. Pass 1: Download thumbnails and biometrically verify against input face.
    3. Pass 2 (fallback): Extract names from titles → search social → verify photos.
    4. Resolve social posts to true profiles.
    5. Rank by Profile > Post > Generic, and by facial similarity distance.
    """
    raw_matches = multi_engine_search(face_crop_path, image_url)
    if not raw_matches:
        return SearchResult()
        
    all_matches = []
    for rm in raw_matches:
        sm = SearchMatch(
            url=rm.url,
            title=rm.title,
            source=rm.source,
            thumbnail=rm.thumbnail,
            is_social=_is_social_domain(rm.url),
            is_profile=_is_social_profile(rm.url),
            engine=rm.engine,
        )
        all_matches.append(sm)

    # ── Pass 1: Thumbnail biometric verification ──
    # Check at most 30 candidates to prevent hanging on 100+ results
    print(f"  [Pass 1] Biometrically checking candidate thumbnails (max 30)...")
    verified_matches = []
    
    # Prioritize Instagram for faster resolution if they match
    sorted_for_verification = sorted(all_matches[:30], key=lambda m: 0 if 'instagram.com' in m.url else 1)
    
    checked = 0
    for match in sorted_for_verification:
        if not match.thumbnail:
            continue
            
        verify_res = verify_face_from_url(input_encoding, match.thumbnail)
        if verify_res.error:
            continue
        
        checked += 1
        print(f"    - Checked: {match.title[:40]} | Dist: {verify_res.distance:.4f} | Src: {match.source}")
            
        if verify_res.is_match:
            print(f"    ✓ Verified match: {match.title[:30]}... (Dist: {verify_res.distance})")
            match.distance = verify_res.distance
            verified_matches.append(match)
            if len(verified_matches) >= 5:
                break

    if not verified_matches:
        print(f"  [Pass 1] No thumbnails passed verification ({checked} checked).")
        
        # ── Pass 2: Name extraction fallback ──
        print()
        print(f"  [Pass 2] Extracting candidate names from {len(all_matches)} result titles...")
        
        from src.name_extractor import extract_names_from_titles
        from src.name_search import search_by_name_and_verify
        
        titles = [m.title for m in all_matches if m.title and m.title != "Unknown"]
        candidate_names = extract_names_from_titles(titles)
        
        if candidate_names:
            print(f"  [Pass 2] Candidate names: {candidate_names}")
            result = search_by_name_and_verify(candidate_names, input_encoding)
            
            if result:
                url, title, distance = result
                name_match = SearchMatch(
                    url=url,
                    title=title,
                    source="name_search",
                    is_social=_is_social_domain(url),
                    is_profile=_is_social_profile(url),
                    engine="name_search",
                    distance=distance,
                )
                verified_matches.append(name_match)
        else:
            print(f"  [Pass 2] No candidate names found in titles.")

    if not verified_matches:
        print("  [Verifier] No matches found via thumbnail or name-based search.")
        return SearchResult(all_matches=all_matches)

    # ── Name-based direct profile search ──
    # Extract the person's name from verified match titles and search for
    # their actual social profile directly. This is far more reliable than
    # trying to resolve a post URL → profile URL (which can land on fan pages).
    from src.name_extractor import extract_names_from_titles
    from src.name_search import search_by_name_and_verify
    
    verified_titles = [m.title for m in verified_matches if m.title and m.title != "Unknown"]
    all_titles = [m.title for m in all_matches if m.title and m.title != "Unknown"]
    candidate_names = extract_names_from_titles(all_titles, verified_titles=verified_titles)
    
    if candidate_names:
        print(f"  [NameSearch] Extracted person name(s): {candidate_names[:5]}")
        name_result = search_by_name_and_verify(candidate_names[:5], input_encoding)
        
        if name_result:
            url, title, distance = name_result
            print(f"  [NameSearch] ✓ Found verified profile: {url} (dist={distance:.4f})")
            name_match = SearchMatch(
                url=url,
                title=title,
                source="name_search",
                is_social=_is_social_domain(url),
                is_profile=_is_social_profile(url),
                engine="name_search",
                distance=distance,
            )
            # Insert at the front — name-based profiles are the most reliable
            verified_matches.insert(0, name_match)
        else:
            print(f"  [NameSearch] No verified profile found via name search.")
    
    # ── Fallback: Post-to-profile resolution + re-verification ──
    # Only for matches that are social posts (not already profiles)
    from src.profile_resolver import resolve_profile
    
    revalidated = []
    for match in verified_matches:
        if match.is_social and not match.is_profile:
            resolved_url, resolved_title = resolve_profile(match.url, match.title)
            if resolved_url != match.url:
                print(f"  [Resolver] Upgraded: {match.url[:40]} → {resolved_url[:50]}")
                
                recheck = _reverify_profile(resolved_url, resolved_title, input_encoding)
                if recheck is not None:
                    if recheck.is_match:
                        print(f"  [Resolver] ✓ Profile photo VERIFIED (dist={recheck.distance:.4f})")
                        match.url = resolved_url
                        match.title = resolved_title
                        match.is_profile = True
                        match.distance = recheck.distance
                    else:
                        print(f"  [Resolver] ✗ Profile photo REJECTED (dist={recheck.distance:.4f}) — wrong person")
                else:
                    print(f"  [Resolver] ? Could not verify profile photo. Keeping original post URL.")
        
        revalidated.append(match)
    
    verified_matches = revalidated

    # Sort: profiles first, then KG/name_search profiles above resolver ones,
    # then by distance. This ensures Knowledge Graph verified official accounts
    # beat fan pages that happen to repost the person's photos.
    verified_matches.sort(key=lambda m: (
        not m.is_profile,            # profiles first
        m.engine != "name_search",   # KG profiles above resolver profiles
        m.distance,                  # then by biometric distance
    ))
    
    best_match = verified_matches[0]
    
    marker = " [PROFILE]" if best_match.is_profile else (" [SOCIAL POST]" if best_match.is_social else "")
    print(f"  Best match{marker}: {best_match.title} ({best_match.engine})")
    print(f"  URL: {best_match.url}")

    return SearchResult(best_match=best_match, all_matches=all_matches)


def _reverify_profile(profile_url: str, profile_title: str, input_encoding: list):
    """Try to find and verify a profile photo from a resolved social profile.
    
    Uses a more lenient tolerance (0.55) than cold matching because we already
    have strong evidence this is the right person from the post thumbnail.
    Profile photos often differ from post photos in angle/lighting/age.
    
    Returns a VerifyResult if a photo could be checked, None if no photo found.
    """
    import requests as _requests
    
    # Re-verification tolerance: more lenient than cold matching (0.45)
    # since we already have evidence from the post thumbnail.
    REVERIFY_TOLERANCE = 0.55
    
    # Try to get profile photo via Google Images search for the profile
    username = profile_url.rstrip("/").split("/")[-1]
    domain = ""
    if "instagram.com" in profile_url:
        domain = "instagram"
    elif "x.com" in profile_url or "twitter.com" in profile_url:
        domain = "twitter"
    elif "youtube.com" in profile_url:
        domain = "youtube"
    elif "linkedin.com" in profile_url:
        domain = "linkedin"
    
    if not username or not domain:
        return None
    
    # Search for the profile photo
    query = f"{username} {domain} profile photo"
    try:
        resp = _requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google_images",
                "q": query,
                "num": 10,
                "api_key": config.SERPAPI_API_KEY,
            },
            timeout=10,
        )
        data = resp.json()
        
        best_result = None
        for img in data.get("images_results", []):
            thumb = img.get("thumbnail", "")
            if thumb:
                result = verify_face_from_url(input_encoding, thumb, tolerance=REVERIFY_TOLERANCE)
                if not result.error:
                    if best_result is None or result.distance < best_result.distance:
                        best_result = result
                    if result.is_match:
                        return result  # Found a good match, return immediately
        
        return best_result  # Return best even if not a match (for rejection logging)
    except Exception:
        pass
    
    return None

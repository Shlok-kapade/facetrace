"""Face verification: compare a candidate web image to the input face encoding.

Downloads candidate match images and runs face_recognition to verify
that the person in the search result is actually the same person as the input.
Rejects false positives where Google/Yandex returned a visually similar
but different person.
"""

import io
import tempfile
from dataclasses import dataclass
from typing import Optional

import requests
import numpy as np
import face_recognition


@dataclass
class VerifyResult:
    """Result of face verification against a candidate image."""
    is_match: bool
    distance: float  # Euclidean distance (lower = better)
    confidence: float  # 0-100%
    error: str = ""


from src.config import config

def verify_face_from_url(
    input_encoding: list,
    candidate_url: str,
    tolerance: float = None,
) -> VerifyResult:
    if tolerance is None:
        tolerance = config.FACE_MATCH_TOLERANCE
    """
    Download an image from a URL, detect faces in it, and compare
    against the input encoding.

    Args:
        input_encoding: 128-d face encoding of the input face.
        candidate_url: URL of the candidate image to verify.
        tolerance: Maximum distance to consider a match.

    Returns:
        VerifyResult with match status and confidence.
    """
    try:
        # Download the image
        resp = requests.get(candidate_url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; FaceVerify/1.0)"
        })
        resp.raise_for_status()

        # Load into face_recognition
        img_data = io.BytesIO(resp.content)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
            tmp.write(img_data.getvalue())
            tmp.flush()
            image = face_recognition.load_image_file(tmp.name)

        # Detect faces
        face_locations = face_recognition.face_locations(image, model="hog")
        if not face_locations:
            return VerifyResult(
                is_match=False, distance=1.0, confidence=0.0,
                error="No face detected in candidate image"
            )

        # Get encodings for all detected faces
        encodings = face_recognition.face_encodings(image, face_locations)
        if not encodings:
            print(f"[Debug] Could not encode face in candidate image: {candidate_url}")
            return VerifyResult(
                is_match=False, distance=1.0, confidence=0.0,
                error="Could not encode face in candidate image"
            )

        # Compare input encoding against all faces found
        input_enc = np.array(input_encoding)
        best_distance = float("inf")

        for enc in encodings:
            distance = np.linalg.norm(input_enc - enc)
            if distance < best_distance:
                best_distance = distance

        is_match = best_distance <= tolerance
        confidence = max(0.0, min(100.0, (1.0 - best_distance / tolerance) * 100.0))

        print(f"[Debug] Verification result for {candidate_url}: match={is_match}, dist={best_distance:.4f}")
        return VerifyResult(
            is_match=is_match,
            distance=round(best_distance, 4),
            confidence=round(confidence, 1),
        )

    except requests.RequestException as e:
        print(f"[Debug] Download failed for {candidate_url}: {e}")
        return VerifyResult(
            is_match=False, distance=1.0, confidence=0.0,
            error=f"Download failed: {e}"
        )
    except Exception as e:
        print(f"[Debug] Verification error for {candidate_url}: {e}")
        return VerifyResult(
            is_match=False, distance=1.0, confidence=0.0,
            error=f"Verification error: {e}"
        )


def verify_face_from_matches(
    input_encoding: list,
    candidate_thumbnails: list,
    tolerance: float = None,
    max_checks: int = 3,
) -> Optional[VerifyResult]:
    if tolerance is None:
        tolerance = config.FACE_MATCH_TOLERANCE
    """
    Try verifying against multiple candidate thumbnails.
    Returns the best match, or None if no thumbnails could be verified.

    Args:
        input_encoding: 128-d face encoding of the input face.
        candidate_thumbnails: List of image URLs to check.
        tolerance: Maximum distance to consider a match.
        max_checks: Maximum number of candidates to check.

    Returns:
        Best VerifyResult or None.
    """
    best_result = None

    for url in candidate_thumbnails[:max_checks]:
        if not url:
            continue
        result = verify_face_from_url(input_encoding, url, tolerance)
        if result.error:
            continue
        if best_result is None or result.distance < best_result.distance:
            best_result = result
        if result.is_match:
            break  # Found a strong match, no need to check more

    return best_result

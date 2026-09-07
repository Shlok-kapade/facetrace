"""Stage 3: Cryptographic fingerprinting of the verification record."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class FingerprintResult:
    """Result from the fingerprinting stage."""
    record: dict
    record_hash: str
    record_json: str  # canonical JSON string


def _hash_file(filepath: str) -> str:
    """Compute SHA-256 hash of a file contents."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _hash_encoding(encoding: list) -> str:
    """Compute SHA-256 hash of the face encoding vector."""
    encoding_str = json.dumps(encoding, sort_keys=True)
    return hashlib.sha256(encoding_str.encode("utf-8")).hexdigest()


def create_fingerprint(
    source_url: str,
    page_title: str,
    face_crop_path: str,
    face_encoding: list,
    matched_image_url: str = "",
) -> FingerprintResult:
    """
    Build a canonical record and compute its SHA-256 fingerprint.

    The record contains all verification metadata. The hash is computed
    from a canonicalized JSON representation (sorted keys, no extra whitespace)
    so it can be independently reproduced for re-verification.

    Args:
        source_url: URL of the matched social/web page.
        page_title: Title of the matched page.
        face_crop_path: Path to the cropped face image file.
        face_encoding: 128-d face encoding vector.
        matched_image_url: URL of the matched image (if available).

    Returns:
        FingerprintResult with the record dict, hash, and canonical JSON.
    """
    print(f"  Building canonical verification record...")

    # Build the record
    record = {
        "source_url": source_url,
        "page_title": page_title,
        "face_crop_hash": _hash_file(face_crop_path),
        "face_encoding_hash": _hash_encoding(face_encoding),
        "matched_image_url": matched_image_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Canonical JSON: sorted keys, no extra whitespace, UTF-8
    record_json = json.dumps(record, sort_keys=True, separators=(",", ":"))
    record_hash = hashlib.sha256(record_json.encode("utf-8")).hexdigest()

    print(f"  Record fields: {list(record.keys())}")
    print(f"  SHA-256 fingerprint: {record_hash}")

    return FingerprintResult(
        record=record,
        record_hash=record_hash,
        record_json=record_json,
    )

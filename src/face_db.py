"""Local SQLite face database for storing and matching face encodings.

Enables identification of previously-seen faces (famous or not) without
any external API call. Uses face_recognition's Euclidean distance for matching.
"""

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import face_recognition

from src.config import config


@dataclass
class FaceDBMatch:
    """A match from the local face database."""
    face_id: int
    name: str
    url: str
    distance: float  # Lower = better match (0.0 = identical)
    confidence: float  # 0-100%, higher = better
    metadata: dict


def _ensure_db():
    """Create the database and table if they don't exist."""
    os.makedirs(os.path.dirname(config.FACE_DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(config.FACE_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS faces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT DEFAULT '',
            encoding TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def lookup(encoding: list, tolerance: float = None) -> Optional[FaceDBMatch]:
    """
    Search the local face database for a matching encoding.

    Args:
        encoding: 128-d face encoding vector.
        tolerance: Maximum Euclidean distance to consider a match.
                   Defaults to config.FACE_MATCH_TOLERANCE.

    Returns:
        FaceDBMatch if found, None otherwise.
    """
    if tolerance is None:
        tolerance = config.FACE_MATCH_TOLERANCE

    conn = _ensure_db()
    cursor = conn.execute("SELECT id, name, url, encoding, metadata FROM faces")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return None

    input_encoding = np.array(encoding)
    best_match = None
    best_distance = float("inf")

    for row in rows:
        face_id, name, url, enc_json, meta_json = row
        stored_encoding = np.array(json.loads(enc_json))

        # Compute Euclidean distance (same as face_recognition.face_distance)
        distance = np.linalg.norm(input_encoding - stored_encoding)

        if distance < tolerance and distance < best_distance:
            best_distance = distance
            confidence = max(0.0, min(100.0, (1.0 - distance / tolerance) * 100.0))
            best_match = FaceDBMatch(
                face_id=face_id,
                name=name,
                url=url,
                distance=round(distance, 4),
                confidence=round(confidence, 1),
                metadata=json.loads(meta_json),
            )

    return best_match


def register(
    encoding: list,
    name: str,
    url: str = "",
    metadata: dict = None,
) -> int:
    """
    Register a new face in the local database.

    Args:
        encoding: 128-d face encoding vector.
        name: Identity name (e.g. "Sharon Verma" or "Unknown #3").
        url: Associated social/web URL.
        metadata: Optional dict of extra info (search engine, etc.).

    Returns:
        The face_id of the newly registered entry.
    """
    if metadata is None:
        metadata = {}

    conn = _ensure_db()
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """INSERT INTO faces (name, url, encoding, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            name,
            url,
            json.dumps(encoding),
            json.dumps(metadata),
            now,
            now,
        ),
    )
    conn.commit()
    face_id = cursor.lastrowid
    conn.close()
    return face_id


def update(face_id: int, name: str = None, url: str = None, metadata: dict = None):
    """Update an existing face record."""
    conn = _ensure_db()
    now = datetime.now(timezone.utc).isoformat()

    if name is not None:
        conn.execute("UPDATE faces SET name = ?, updated_at = ? WHERE id = ?", (name, now, face_id))
    if url is not None:
        conn.execute("UPDATE faces SET url = ?, updated_at = ? WHERE id = ?", (url, now, face_id))
    if metadata is not None:
        conn.execute("UPDATE faces SET metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(metadata), now, face_id))

    conn.commit()
    conn.close()


def count() -> int:
    """Return total number of faces in the database."""
    conn = _ensure_db()
    cursor = conn.execute("SELECT COUNT(*) FROM faces")
    n = cursor.fetchone()[0]
    conn.close()
    return n


def get_next_unknown_id() -> int:
    """Get the next sequential unknown ID number."""
    conn = _ensure_db()
    cursor = conn.execute("SELECT COUNT(*) FROM faces WHERE name LIKE 'Unknown #%'")
    n = cursor.fetchone()[0]
    conn.close()
    return n + 1

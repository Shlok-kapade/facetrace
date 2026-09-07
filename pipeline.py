#!/usr/bin/env python3
"""Face Identification & Blockchain Verification -- Pipeline Orchestrator.

Runs all 7 stages end-to-end:
  1. Face Detection & Encoding
  2. Local Face DB Lookup
  3. Multi-Engine Web Search
  4. Profile Resolution & Face Verification
  5. Cryptographic Fingerprinting
  6. Blockchain Upload
  7. On-Chain Re-Verification

Usage:
    python pipeline.py --input sample_data/input_face.jpg
"""

import argparse
import hashlib
import json
import sys
import time
from urllib.parse import urlparse

from src.face_stage import detect_and_encode
from src.fingerprint_stage import create_fingerprint
from src.chain_client import ChainClient
from src import face_db


def print_banner():
    print()
    print("=" * 65)
    print("  Face Identification & Blockchain Verification Pipeline")
    print("  HH Goa 2026 -- Task 3 (Multi-Source Edition)")
    print("=" * 65)
    print()


def print_stage(num, total, title):
    print()
    print("-" * 65)
    print(f"  [{num}/{total}] {title}")
    print("-" * 65)


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Source Face Identification & Blockchain Verification Pipeline"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the input face image",
    )
    parser.add_argument(
        "--image-url",
        default=None,
        help="Optional: pre-existing public URL for the face image (skips upload step)",
    )
    args = parser.parse_args()

    print_banner()
    start_time = time.time()

    # -- Stage 1: Face Detection & Encoding --
    print_stage(1, 7, "Face Detection & Encoding")
    try:
        face_result = detect_and_encode(args.input)
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR Stage 1 failed: {e}")
        sys.exit(1)

    # Variables to hold the final identity
    identity_url = ""
    identity_title = ""
    identity_thumbnail = ""
    db_match_confidence = 0.0

    # -- Stage 2: Local Face DB Lookup --
    print_stage(2, 7, "Local Face Database Lookup")
    db_match = face_db.lookup(face_result.encoding)
    if db_match:
        print(f"  MATCH FOUND IN LOCAL DATABASE!")
        print(f"  Identity: {db_match.name}")
        print(f"  URL:      {db_match.url}")
        print(f"  Confidence: {db_match.confidence}% (distance: {db_match.distance})")
        
        identity_url = db_match.url
        identity_title = db_match.name
        db_match_confidence = db_match.confidence
        # Skip web search
        skip_web_search = True
    else:
        print(f"  No match in local database. Will proceed to web search.")
        skip_web_search = False

    if not skip_web_search:
        # -- Stage 3: Multi-Engine Web Search & Verification --
        print_stage(3, 7, "Multi-Engine Web Search (SerpApi)")
        from src.search_stage import search_and_verify
        try:
            search_result = search_and_verify(
                args.input,
                face_result.encoding,
                image_url=args.image_url,
            )
        except RuntimeError as e:
            print(f"  ERROR Stage 3 failed: {e}")
            sys.exit(1)

        match = search_result.best_match

        if match:
            # We found a biometrically verified match!
            identity_url = match.url
            identity_title = match.title
            identity_thumbnail = match.thumbnail
            confidence = max(0.0, min(100.0, (1.0 - match.distance / face_db.config.FACE_MATCH_TOLERANCE) * 100.0))
            
            # Register in local DB
            print(f"  Registering newly identified person in local database...")
            face_id = face_db.register(
                encoding=face_result.encoding,
                name=match.title,
                url=match.url,
                metadata={"engine": match.engine, "verified_confidence": confidence}
            )
            print(f"  Registered as DB ID #{face_id}")

        if not match:
            print()
            print("  WARNING: No web matches found for this face, or matches were rejected as look-alikes.")
            
            next_id = face_db.get_next_unknown_id()
            unknown_name = f"Unknown #{next_id}"
            print(f"  Registering person as '{unknown_name}' in local database...")
            
            face_id = face_db.register(
                encoding=face_result.encoding,
                name=unknown_name,
                url="",
                metadata={"status": "unknown"}
            )
            print(f"  Registered as DB ID #{face_id}")
            
            identity_url = f"local://db/faces/{face_id}"
            identity_title = unknown_name

    # -- Stage 5: Cryptographic Fingerprinting --
    print_stage(5, 7, "Cryptographic Fingerprinting")
    fp_result = create_fingerprint(
        source_url=identity_url,
        page_title=identity_title,
        face_crop_path=face_result.face_crop_path,
        face_encoding=face_result.encoding,
        matched_image_url=identity_thumbnail,
    )

    # -- Stage 6: Blockchain Upload --
    print_stage(6, 7, "Blockchain Upload")
    chain = ChainClient()
    chain.setup_local_chain()
    chain.deploy_contract()
    upload_result = chain.add_record(identity_url, fp_result.record_hash)

    # -- Stage 7: On-Chain Re-Verification --
    print_stage(7, 7, "On-Chain Re-Verification")
    print("  Re-computing hash independently from original record data...")

    recomputed_json = json.dumps(fp_result.record, sort_keys=True, separators=(",", ":"))
    recomputed_hash = hashlib.sha256(recomputed_json.encode("utf-8")).hexdigest()
    print(f"  Recomputed hash: {recomputed_hash}")

    verification = chain.verify_record(upload_result.record_id, recomputed_hash)

    # -- Final Summary --
    elapsed = time.time() - start_time
    print()
    print("=" * 65)
    print("  PIPELINE COMPLETE -- SUMMARY")
    print("=" * 65)
    print(f"  Input image:       {args.input}")
    print(f"  Faces detected:    {face_result.num_faces_detected}")
    print(f"  Identity:          {identity_title}")
    print(f"  Identity URL:      {identity_url}")
    if db_match_confidence > 0:
        print(f"  Match Source:      Local Database (Confidence: {db_match_confidence}%)")
    elif "local://" in identity_url:
        print(f"  Match Source:      Registered as new Unknown")
    else:
        print(f"  Match Source:      Web Search (Verified)")
    print(f"  Record hash:       {fp_result.record_hash}")
    print(f"  Blockchain:        Local Ethereum (eth-tester)")
    print(f"  Contract:          {upload_result.contract_address}")
    print(f"  Record ID:         {upload_result.record_id}")
    print(f"  Tx hash:           {upload_result.tx_hash}")
    print()
    if verification.is_verified:
        print("  +---------------------------------------------------+")
        print("  |  VERIFICATION: PASSED                             |")
        print("  |  The on-chain record matches the original data.   |")
        print("  |  Record is authentic and untampered.              |")
        print("  +---------------------------------------------------+")
    else:
        print("  +---------------------------------------------------+")
        print("  |  VERIFICATION: FAILED                             |")
        print("  |  Hash mismatch detected -- possible tampering!    |")
        print("  +---------------------------------------------------+")
    print()
    print(f"  Total time: {elapsed:.1f}s")
    print("=" * 65)
    print()


if __name__ == "__main__":
    main()

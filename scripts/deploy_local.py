#!/usr/bin/env python3
"""Standalone script to compile and deploy FaceVerification contract to local chain.

Usage:
    python scripts/deploy_local.py

Note: Since eth-tester uses an in-memory chain, the deployment is ephemeral.
The pipeline.py script handles deployment automatically during each run.
This script is for testing/validation of the contract independently.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.chain_client import ChainClient


def main():
    print("=" * 60)
    print("FaceVerification Contract -- Local Deployment")
    print("=" * 60)
    print()

    client = ChainClient()

    # Setup chain and deploy
    client.setup_local_chain()
    address = client.deploy_contract()

    print()
    print("-- Testing contract with a sample record --")
    print()

    # Test: add a record
    test_url = "https://instagram.com/test_user"
    test_hash = "abc123def456" * 5 + "abcd"  # 64-char fake hash
    result = client.add_record(test_url, test_hash)

    print()
    print("-- Testing verification --")
    print()

    # Test: verify the record
    verification = client.verify_record(result.record_id, test_hash)

    print()
    if verification.is_verified:
        print("All tests passed! Contract is working correctly.")
    else:
        print("Verification failed -- something is wrong.")
        sys.exit(1)

    # Test: negative case (tampered hash)
    print()
    print("-- Testing tamper detection --")
    print()
    tampered_hash = "0" * 64
    bad_verification = client.verify_record(result.record_id, tampered_hash)
    if not bad_verification.is_verified:
        print("Tamper detection works! Mismatched hash correctly rejected.")
    else:
        print("Tamper detection failed -- false positive.")
        sys.exit(1)

    print()
    print("=" * 60)
    print(f"Contract address: {address}")
    print("Local deployment test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

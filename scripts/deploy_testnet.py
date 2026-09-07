#!/usr/bin/env python3
"""Stretch goal: Deploy FaceVerification contract to Polygon Amoy testnet.

Requires:
  - POLYGON_RPC_URL in .env (e.g., from Alchemy/Infura free tier)
  - PRIVATE_KEY in .env (funded testnet wallet)

Usage:
    python scripts/deploy_testnet.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solcx import compile_source, install_solc
from web3 import Web3
from src.config import config


def main():
    print("=" * 60)
    print("FaceVerification Contract -- Polygon Amoy Testnet Deployment")
    print("=" * 60)
    print()

    if not config.POLYGON_RPC_URL:
        print("POLYGON_RPC_URL not set in .env")
        print("   Get a free RPC URL from https://www.alchemy.com or https://infura.io")
        sys.exit(1)

    if not config.PRIVATE_KEY:
        print("PRIVATE_KEY not set in .env")
        print("   Use a testnet-only wallet with Amoy MATIC from a faucet")
        sys.exit(1)

    # Connect to Polygon Amoy
    print(f"  Connecting to: {config.POLYGON_RPC_URL[:50]}...")
    w3 = Web3(Web3.HTTPProvider(config.POLYGON_RPC_URL))

    if not w3.is_connected():
        print("Could not connect to Polygon Amoy RPC")
        sys.exit(1)

    account = w3.eth.account.from_key(config.PRIVATE_KEY)
    balance = w3.eth.get_balance(account.address)
    print(f"  Connected! Account: {account.address}")
    print(f"  Balance: {w3.from_wei(balance, "ether")} MATIC")

    if balance == 0:
        print("Account has no MATIC. Get testnet MATIC from:")
        print("   https://faucet.polygon.technology/")
        sys.exit(1)

    # Compile
    print()
    solc_version = "0.8.19"
    install_solc(solc_version)

    contracts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "contracts",
    )
    sol_path = os.path.join(contracts_dir, "FaceVerification.sol")

    with open(sol_path, "r") as f:
        source = f.read()

    compiled = compile_source(
        source,
        output_values=["abi", "bin"],
        solc_version=solc_version,
    )
    contract_id, contract_interface = next(
        (k, v) for k, v in compiled.items() if "FaceVerification" in k
    )
    abi = contract_interface["abi"]
    bytecode = contract_interface["bin"]
    print(f"  Contract compiled successfully")

    # Deploy
    print("  Deploying to Polygon Amoy...")
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    # Build transaction
    nonce = w3.eth.get_transaction_count(account.address)
    tx = Contract.constructor().build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 1000000,
        "gasPrice": w3.to_wei("30", "gwei"),
    })

    # Sign and send
    signed_tx = w3.eth.account.sign_transaction(tx, config.PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"  Tx sent: {tx_hash.hex()}")
    print(f"  Waiting for confirmation...")

    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    contract_address = tx_receipt.contractAddress

    print()
    print("=" * 60)
    print(f"  Contract deployed on Polygon Amoy!")
    print(f"  Address: {contract_address}")
    print(f"  Tx hash: {tx_hash.hex()}")
    print(f"  Block:   {tx_receipt.blockNumber}")
    print(f"  Explorer: https://amoy.polygonscan.com/address/{contract_address}")
    print("=" * 60)

    # Save contract data
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "contract_data_testnet.json",
    )
    with open(data_path, "w") as f:
        json.dump({
            "address": contract_address,
            "abi": abi,
            "deploy_tx": tx_hash.hex(),
            "chain": "polygon-amoy",
            "explorer": f"https://amoy.polygonscan.com/address/{contract_address}",
        }, f, indent=2)
    print(f"  Contract data saved to {data_path}")


if __name__ == "__main__":
    main()

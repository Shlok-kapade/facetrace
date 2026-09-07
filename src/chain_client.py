"""Blockchain client — Polygon Amoy Testnet via web3.py.

Uses Polygon Amoy testnet (no local emulator, no paid API key needed).
The public RPC endpoint works out of the box — no Infura/Alchemy required.

Requires in .env:
  - ETH_PRIVATE_KEY : Your wallet private key (needs Amoy MATIC from faucet)
  - ETH_RPC_URL     : (optional) override RPC. Default: public Polygon Amoy RPC
  - ETH_CONTRACT_ADDRESS : (optional) reuse already-deployed contract

First run deploys the FaceVerification contract and saves its address to
contract_data.json so subsequent runs skip redeployment (saves gas & time).
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from solcx import compile_source, install_solc
from web3 import Web3
from web3.middleware import geth_poa_middleware

from src.config import config


# ── Polygon Amoy Testnet constants ─────────────────────────────────────────
AMOY_CHAIN_ID = 80002
AMOY_PUBLIC_RPC = "https://rpc-amoy.polygon.technology"
EXPLORER_BASE = "https://amoy.polygonscan.com"

SOLC_VERSION = "0.8.19"
CONTRACT_DIR = Path(__file__).parent.parent / "contracts"
CONTRACT_DATA_PATH = Path(__file__).parent.parent / "contract_data.json"


@dataclass
class UploadResult:
    """Result from blockchain upload."""
    record_id: int
    tx_hash: str
    contract_address: str
    block_number: int
    explorer_url: str


@dataclass
class VerificationResult:
    """Result from on-chain re-verification."""
    is_verified: bool
    onchain_hash: str
    recomputed_hash: str
    onchain_url: str
    onchain_timestamp: int
    onchain_submitter: str


def _connect() -> Web3:
    """Connect to Polygon Amoy via RPC (public endpoint or override from .env)."""
    rpc = config.ETH_RPC_URL or AMOY_PUBLIC_RPC
    print(f"  RPC: {rpc}")

    w3 = Web3(Web3.HTTPProvider(rpc))
    # Polygon uses Proof-of-Authority — this middleware is required
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)

    if not w3.is_connected():
        raise RuntimeError(
            f"Cannot connect to Polygon Amoy node at {rpc}\n"
            "Check your internet connection or try a different RPC in .env:\n"
            "  ETH_RPC_URL=https://rpc-amoy.polygon.technology"
        )
    return w3


def _get_account(w3: Web3):
    """Load the signing account from the private key in .env."""
    pk = config.ETH_PRIVATE_KEY
    if not pk:
        raise RuntimeError(
            "ETH_PRIVATE_KEY not set in .env\n"
            "Export your MetaMask private key and add it to .env"
        )
    if not pk.startswith("0x"):
        pk = "0x" + pk
    return w3.eth.account.from_key(pk)


def _compile_contract() -> tuple:
    """Compile FaceVerification.sol and return (bytecode, abi)."""
    print(f"  Installing Solidity compiler v{SOLC_VERSION}...")
    install_solc(SOLC_VERSION)

    sol_path = CONTRACT_DIR / "FaceVerification.sol"
    print(f"  Compiling {sol_path.name}...")
    with open(sol_path) as f:
        source = f.read()

    compiled = compile_source(source, output_values=["abi", "bin"], solc_version=SOLC_VERSION)
    _, contract_interface = next((k, v) for k, v in compiled.items() if "FaceVerification" in k)
    return contract_interface["bin"], contract_interface["abi"]


def _sign_and_send(w3: Web3, account, tx: dict) -> bytes:
    """Sign a transaction with the private key and broadcast it."""
    tx["chainId"] = AMOY_CHAIN_ID
    tx["nonce"] = w3.eth.get_transaction_count(account.address)

    # Use legacy gas pricing (more compatible with Amoy public RPC)
    tx["gasPrice"] = w3.eth.gas_price
    tx.pop("maxFeePerGas", None)
    tx.pop("maxPriorityFeePerGas", None)

    if "gas" not in tx or not tx["gas"]:
        tx["gas"] = w3.eth.estimate_gas(tx)

    signed = account.sign_transaction(tx)
    return w3.eth.send_raw_transaction(signed.rawTransaction)


class ChainClient:
    """Manages Polygon Amoy testnet connection, contract deployment, and record management."""

    def __init__(self):
        self.w3: Web3 = None
        self.account = None
        self.contract = None
        self._contract_address = ""
        self._abi = None

    def setup_local_chain(self):
        """Connect to Polygon Amoy testnet (name kept for pipeline compatibility)."""
        print("  Connecting to Polygon Amoy Testnet...")
        self.w3 = _connect()
        self.account = _get_account(self.w3)

        balance_wei = self.w3.eth.get_balance(self.account.address)
        balance_matic = self.w3.from_wei(balance_wei, "ether")
        chain_id = self.w3.eth.chain_id

        print(f"  Connected — Chain ID: {chain_id} (Polygon Amoy)")
        print(f"  Wallet:  {self.account.address}")
        print(f"  Balance: {balance_matic:.6f} MATIC")

        if balance_matic < 0.01:
            print("  WARNING: Low balance!")
            print("  Get free MATIC at: https://faucet.polygon.technology")
            print("  (Login with Google → paste wallet address → receive 0.5 MATIC)")

    def deploy_contract(self):
        """Deploy the contract, or reuse existing address from env / contract_data.json."""
        if not self.w3:
            self.setup_local_chain()

        # 1. Check .env override
        addr = config.ETH_CONTRACT_ADDRESS.strip()

        # 2. Check saved contract_data.json
        if not addr and CONTRACT_DATA_PATH.exists():
            try:
                saved = json.loads(CONTRACT_DATA_PATH.read_text())
                if saved.get("chain_id") == AMOY_CHAIN_ID and saved.get("address"):
                    addr = saved["address"]
                    print(f"  Reusing previously deployed contract: {addr}")
            except Exception:
                pass

        bytecode, abi = _compile_contract()
        self._abi = abi

        if addr:
            code = self.w3.eth.get_code(self.w3.to_checksum_address(addr))
            if code and code != b"":
                self._contract_address = self.w3.to_checksum_address(addr)
                self.contract = self.w3.eth.contract(address=self._contract_address, abi=abi)
                print(f"  Contract loaded at {self._contract_address}")
                print(f"  Explorer: {EXPLORER_BASE}/address/{self._contract_address}")
                return self._contract_address
            else:
                print(f"  WARNING: Address {addr} has no bytecode — deploying fresh.")

        # Deploy fresh
        print("  Deploying FaceVerification contract to Polygon Amoy...")
        Contract = self.w3.eth.contract(abi=abi, bytecode=bytecode)
        deploy_tx = Contract.constructor().build_transaction({"from": self.account.address})
        tx_hash_bytes = _sign_and_send(self.w3, self.account, deploy_tx)
        print(f"  Deploy tx sent: {tx_hash_bytes.hex()}")
        print("  Waiting for confirmation (usually 5-15 seconds on Amoy)...")

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=300)
        self._contract_address = receipt["contractAddress"]
        self.contract = self.w3.eth.contract(address=self._contract_address, abi=abi)

        print(f"  Contract deployed at: {self._contract_address}")
        print(f"  Block: #{receipt['blockNumber']}")
        print(f"  Explorer: {EXPLORER_BASE}/address/{self._contract_address}")

        # Save for reuse
        data = {
            "address": self._contract_address,
            "chain_id": AMOY_CHAIN_ID,
            "abi": abi,
            "deploy_tx": tx_hash_bytes.hex(),
            "explorer": f"{EXPLORER_BASE}/address/{self._contract_address}",
            "network": "Polygon Amoy Testnet",
        }
        CONTRACT_DATA_PATH.write_text(json.dumps(data, indent=2))
        print(f"  Contract data saved to contract_data.json")
        print(f"  TIP: Set ETH_CONTRACT_ADDRESS={self._contract_address} in .env to skip redeployment.")

        return self._contract_address

    def add_record(self, source_url: str, record_hash: str) -> UploadResult:
        """Submit a verification record to Polygon Amoy blockchain."""
        if not self.contract:
            raise RuntimeError("Contract not deployed. Call deploy_contract() first.")

        print(f"  Submitting record to Polygon Amoy blockchain...")
        print(f"    URL: {source_url}")
        print(f"    Hash: {record_hash}")

        tx = self.contract.functions.addRecord(source_url, record_hash).build_transaction({
            "from": self.account.address,
        })
        tx_hash_bytes = _sign_and_send(self.w3, self.account, tx)
        print(f"  Tx sent: {tx_hash_bytes.hex()}")
        print("  Waiting for confirmation...")

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=300)
        logs = self.contract.events.RecordAdded().process_receipt(receipt)
        record_id = logs[0]["args"]["id"]

        explorer_url = f"{EXPLORER_BASE}/tx/{tx_hash_bytes.hex()}"

        result = UploadResult(
            record_id=record_id,
            tx_hash=tx_hash_bytes.hex(),
            contract_address=self._contract_address,
            block_number=receipt["blockNumber"],
            explorer_url=explorer_url,
        )

        print(f"  Record committed on Polygon Amoy!")
        print(f"    Record ID: #{result.record_id}")
        print(f"    Block:     #{result.block_number}")
        print(f"    Explorer:  {explorer_url}")
        return result

    def verify_record(self, record_id: int, expected_hash: str) -> VerificationResult:
        """Read a record from chain and verify the hash matches."""
        if not self.contract:
            raise RuntimeError("Contract not deployed. Call deploy_contract() first.")

        print(f"  Reading record #{record_id} from Polygon Amoy blockchain...")
        onchain = self.contract.functions.getRecord(record_id).call()

        if hasattr(onchain, "sourceUrl"):
            onchain_url, onchain_hash, onchain_ts, onchain_submitter = (
                onchain.sourceUrl, onchain.recordHash, onchain.timestamp, onchain.submitter
            )
        else:
            onchain_url, onchain_hash, onchain_ts, onchain_submitter = (
                onchain[0], onchain[1], onchain[2], onchain[3]
            )

        is_verified = onchain_hash == expected_hash

        result = VerificationResult(
            is_verified=is_verified,
            onchain_hash=onchain_hash,
            recomputed_hash=expected_hash,
            onchain_url=onchain_url,
            onchain_timestamp=onchain_ts,
            onchain_submitter=onchain_submitter,
        )

        print(f"    On-chain hash:   {onchain_hash}")
        print(f"    Recomputed hash: {expected_hash}")
        print(f"    Submitter:       {onchain_submitter}")

        if is_verified:
            print("  VERIFICATION PASSED — Record is authentic and untampered!")
        else:
            print("  VERIFICATION FAILED — Hash mismatch! Possible tampering.")

        return result

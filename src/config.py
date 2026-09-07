"""Central configuration loaded from .env file."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration loaded from .env file."""

    # ── SerpApi ──
    SERPAPI_API_KEY: str = os.getenv("SERPAPI_API_KEY", "")

    # ── Ethereum / Sepolia Testnet ──
    # Get a free RPC URL from https://infura.io or https://alchemy.com
    ETH_RPC_URL: str = os.getenv("ETH_RPC_URL", "")
    # Your wallet private key (must have Sepolia ETH — get free from faucet.sepolia.dev)
    ETH_PRIVATE_KEY: str = os.getenv("ETH_PRIVATE_KEY", "")
    # After first deploy, paste the address here to reuse the contract
    ETH_CONTRACT_ADDRESS: str = os.getenv("ETH_CONTRACT_ADDRESS", "")

    # ── Face database ──
    FACE_DB_PATH: str = os.getenv("FACE_DB_PATH", "data/faces.db")
    FACE_MATCH_TOLERANCE: float = float(os.getenv("FACE_MATCH_TOLERANCE", "0.45"))

    # ── Social domains ──
    SOCIAL_DOMAINS: list = [
        "instagram.com",
        "x.com",
        "twitter.com",
        "linkedin.com",
        "facebook.com",
        "reddit.com",
        "github.com",
        "medium.com",
        "youtube.com",
        "wikipedia.org",
        "threads.net",
        "pinterest.com",
    ]

    # ── Search engines via SerpApi ──
    SEARCH_ENGINES: list = [
        "google_lens",
        "yandex_images",
        "google_reverse_image",
    ]

    @classmethod
    def validate(cls) -> list:
        """Return list of missing required config values."""
        issues = []
        if not cls.SERPAPI_API_KEY:
            issues.append("SERPAPI_API_KEY not set in .env")
        if not cls.ETH_RPC_URL:
            issues.append("ETH_RPC_URL not set in .env (get free from infura.io)")
        if not cls.ETH_PRIVATE_KEY:
            issues.append("ETH_PRIVATE_KEY not set in .env")
        return issues


config = Config()

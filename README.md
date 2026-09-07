# 🧬 FaceTrace — Face Identification & Blockchain Verification

> Upload a photo. Identify who it is. Prove it on the blockchain — permanently.

FaceTrace is an AI-powered forensic pipeline that identifies a person from a photo using multi-engine reverse image search, biometric face verification, and records the result as a tamper-proof record on the **Polygon Amoy testnet**.

---

## 📸 How It Works

```
Photo → Face Detection → Local DB Lookup → Web Search (Google + Yandex)
     → Biometric Verification → Profile Resolution → SHA-256 Fingerprint
     → Ethereum Blockchain (Sepolia) → On-Chain Re-Verification ✓
```

| Stage | What Happens |
|---|---|
| 1. Face Detection | dlib detects and encodes the face into a 128-dimensional vector |
| 2. Local DB Lookup | Checks if this face was identified before (SQLite cache) |
| 3. Web Search | Queries Google Lens + Yandex via SerpApi reverse image search |
| 4. Biometric Verify | Every candidate result has its profile photo downloaded and face-compared |
| 5. Profile Resolution | Resolves social media post URLs → actual profile URLs via page metadata |
| 6. Fingerprinting | Bundles all evidence into a canonical JSON + SHA-256 hash |
| 7. Blockchain Upload | Commits the hash to the `FaceVerification` Solidity contract on Sepolia |
| 8. Re-Verification | Re-computes hash independently and verifies it matches on-chain |

---

## ⚙️ Prerequisites

### System dependencies (must install before pip packages)

**Ubuntu / Debian / Kali:**
```bash
sudo apt-get update
sudo apt-get install -y cmake build-essential libopenblas-dev liblapack-dev \
                        libx11-dev libgtk-3-dev python3-dev python3-pip python3-venv
```

**macOS:**
```bash
brew install cmake openblas
```

**Windows:**
1. Install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (check "Desktop development with C++")
2. Install [CMake](https://cmake.org/download/) and add it to PATH
3. Then run `pip install dlib` before `face_recognition`

> ⚠️ `face_recognition` uses `dlib` which compiles C++ code. The system deps above are **required** or installation will fail.

---

## 🚀 Quick Start

### 1. Clone and set up Python environment

```bash
git clone https://github.com/yourname/facetrace.git
cd facetrace

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 2. Configure your `.env` file

```bash
cp .env.example .env
# Now open .env and fill in the values (see section below)
```

### 3. Start the web UI

```bash
python app.py
```

Open your browser at **http://localhost:5000** — drag and drop a photo to begin.

---

## 🔑 `.env` Configuration

Copy `.env.example` to `.env` and fill in the following values:

---

### `SERPAPI_API_KEY` — Reverse Image Search

Used to query Google Lens and Yandex reverse image search.

**How to get it:**
1. Go to [serpapi.com](https://serpapi.com) → Sign up (free)
2. Free plan gives you **100 searches/month** — more than enough for demos
3. Go to **Dashboard → API Key** → copy your key

```env
SERPAPI_API_KEY=f115eb4...your_key_here
```

---

### `ETH_RPC_URL` — Ethereum Sepolia RPC Endpoint

This is the URL your app uses to talk to the Ethereum blockchain. You need a free account from Infura or Alchemy.

**Option A — Infura (recommended):**
1. Go to [infura.io](https://infura.io) → Sign up (free, no credit card)
2. Click **Create New API Key** → Select "Web3 API"
3. Go to your project → **Networks** tab → Enable **Sepolia**
4. Copy the HTTPS endpoint — it looks like:
   `https://sepolia.infura.io/v3/abc123your_project_id`

**Option B — Alchemy:**
1. Go to [alchemy.com](https://alchemy.com) → Sign up (free)
2. Click **Create App** → Chain: Ethereum → Network: Sepolia
3. Click **View Key** → copy the HTTPS URL

```env
ETH_RPC_URL=https://sepolia.infura.io/v3/YOUR_PROJECT_ID
```

---

### `ETH_PRIVATE_KEY` — Wallet Private Key

This is the private key of the Ethereum wallet that will sign and submit transactions.

> ⚠️ **IMPORTANT**: Use a **dedicated testnet-only wallet**. Never use your main wallet with real ETH. Create a fresh one just for this.

**How to get it:**
1. Install [MetaMask](https://metamask.io) browser extension
2. Create a new account (or use an existing one)
3. Click the **three dots (⋮)** next to the account name → **Account Details**
4. Click **Export Private Key** → enter your MetaMask password → copy the key

```env
ETH_PRIVATE_KEY=0xabc123your_private_key_here
```

---

### `ETH_PRIVATE_KEY` — Fund Your Wallet with Free Amoy MATIC

Your wallet needs Amoy MATIC to pay gas fees (each transaction costs ~0.0001 ETH).

**Get free Amoy MATIC from faucets:**
- [faucet.polygon.technology](https://faucet.polygon.technology) — paste your wallet address → get 0.5 ETH
- [faucet.polygon.technology](https://faucet.polygon.technology) — requires Alchemy account
- [faucets.chain.link](https://faucets.chain.link/sepolia) — Chainlink faucet

One faucet claim gives you enough for **hundreds of pipeline runs**.

---

### `ETH_CONTRACT_ADDRESS` — Smart Contract Address (optional after first run)

The `FaceVerification` Solidity contract is deployed **automatically on first run**. After deployment, the address is saved to `contract_data.json`.

To avoid redeploying on every run (faster + saves gas), copy the deployed address here:

```env
# Leave blank on first run — the app deploys it automatically
# After first run, copy the address from contract_data.json or from the terminal output
ETH_CONTRACT_ADDRESS=0xYourDeployedContractAddress
```

---

### Complete `.env` example

```env
# SerpApi — reverse image search
SERPAPI_API_KEY=f115eb4d875d7de1fda4f52671c7d4c19b34c42dfe9c370ae54bfa76e2af2959

# Ethereum Sepolia
ETH_RPC_URL=https://sepolia.infura.io/v3/abc123your_project_id
ETH_PRIVATE_KEY=0xabc123your_private_key_here
ETH_CONTRACT_ADDRESS=   # leave blank on first run

# Optional: adjust face matching strictness (lower = stricter)
# FACE_MATCH_TOLERANCE=0.45
```

---

## ⛓️ How the Blockchain Works (Simple Explanation)

Think of it like a **notary stamp** that's cryptographically impossible to fake.

1. **Fingerprint** — After identifying a face, all evidence is bundled:
   - The matched social media URL
   - A hash of the face image crop
   - A hash of the 128-point biometric vector
   - The timestamp of identification

   These are serialized to canonical JSON and **SHA-256 hashed** → one 64-character string.

2. **Upload** — That hash + the URL are submitted to a Solidity smart contract on the **Polygon Amoy testnet** via a signed transaction. The blockchain permanently records it with a transaction hash you can view on [amoy.polygonscan.com](https://amoy.polygonscan.com).

3. **Verify** — The hash is independently recomputed from the original data and compared against what's on-chain. If they match → `VERIFICATION PASSED`. If anyone tampered with the record → hashes won't match → `FAILED`.

**Why it matters:** Investigators, journalists, or security researchers can prove *when* a face was identified, *what* evidence was used, and that **nobody altered the result afterwards** — forever, for free.

---

## 📁 Project Structure

```
facetrace/
├── app.py                    # Flask web server (UI backend)
├── pipeline.py               # CLI pipeline runner
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
├── .env                      # Your config (never commit this!)
│
├── contracts/
│   └── FaceVerification.sol  # Solidity smart contract
├── contract_data.json        # Saved after first deploy (auto-generated)
│
├── src/
│   ├── config.py             # Loads .env variables
│   ├── face_stage.py         # Stage 1: face detection & encoding
│   ├── face_db.py            # Stage 2: local SQLite face cache
│   ├── multi_search.py       # Stage 3: multi-engine reverse image search
│   ├── search_stage.py       # Stage 3-4: search orchestration & verification
│   ├── name_extractor.py     # NLP-based person name extraction from titles
│   ├── name_search.py        # Stage 4: name → social profile search
│   ├── profile_resolver.py   # Stage 4: post URL → profile URL resolution
│   ├── face_verify.py        # Biometric face comparison utilities
│   ├── fingerprint_stage.py  # Stage 5: SHA-256 cryptographic fingerprinting
│   └── chain_client.py       # Stage 6-7: Ethereum Sepolia interaction
│
├── templates/
│   └── index.html            # Web UI
├── uploads/                  # Uploaded images & face crops (auto-created)
├── data/
│   └── faces.db              # Local face database (auto-created)
└── sample_data/              # Test images
```

---

## 🖥️ Running the CLI (without the web UI)

```bash
# Run the full pipeline on a single image
python pipeline.py --input sample_data/ex2.jpg

# Pipeline stages:
# [1/7] Face Detection & Encoding
# [2/7] Local Face Database Lookup
# [3/7] Multi-Engine Web Search (SerpApi)
# [4/7] Profile Resolution & Biometric Verification
# [5/7] Cryptographic Fingerprinting
# [6/7] Blockchain Upload (Sepolia)
# [7/7] On-Chain Re-Verification
```

---

## 🧪 Test Images

| File | Person | Expected Result |
|---|---|---|
| `sample_data/ex1.jpg` | Sharon Verma (stand-up comedian) | Instagram profile found |
| `sample_data/ex2.jpg` | Arjun Kapoor (Bollywood actor) | Knowledge Graph match |
| `sample_data/ex4.jpeg` | BeastBoyShub (YouTuber) | YouTube channel found |
| `sample_data/ex5.jpeg` | Unknown person (no web presence) | Registered as `Unknown #N` |

---

## ❓ Troubleshooting

**`dlib` installation fails:**
Make sure cmake and build tools are installed (see Prerequisites above). On Ubuntu, run `sudo apt-get install cmake build-essential` first.

**`No face detected in the image`:**
Use a clear, well-lit photo where the face is the main subject. Avoid group photos or faces at extreme angles.

**`Cannot connect to Ethereum node`:**
Double-check `ETH_RPC_URL` in your `.env`. Make sure you enabled the Sepolia network in your Infura/Alchemy dashboard.

**`Insufficient funds` / low balance warning:**
Visit one of the faucets listed above to get free Amoy MATIC. You need at least 0.001 ETH per run.

**`ETH_CONTRACT_ADDRESS` not set but contract already deployed:**
Open `contract_data.json` → copy the `address` value → paste it as `ETH_CONTRACT_ADDRESS` in `.env`.

**Pipeline takes too long:**
The web search and biometric verification stages take 2-4 minutes for first-time identification. After a face is identified once, it's cached locally and subsequent lookups are instant (< 1 second).

---

## 🔒 Security Notes

- **Never commit your `.env` file** — it contains your private key. It is listed in `.gitignore`.
- Use a **separate wallet with only testnet ETH** — never expose your main wallet private key.
- The `uploads/` folder stores submitted images — clear it periodically in production.

---

## 📄 License

MIT — Built for HackGoa 2026.

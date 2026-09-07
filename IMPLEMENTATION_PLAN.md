# Face Identification & Blockchain Verification — Implementation Plan
**HH Goa 2026 — Shortlisting Task 3**
**Stack: Python end-to-end** (CV + web search + blockchain interaction via `web3.py`)
**Deadline: Sept 7, 2026, 11:59 PM** — plan assumes ~24-30 working hours.

---

## 0. Key decisions & why

| Decision | Choice | Reason |
|---|---|---|
| Language | Python, end-to-end | Team already doing CV in Python; `web3.py` is mature enough that you don't need a JS/Node split — one less context switch under time pressure |
| Face detection/encoding | `face_recognition` (dlib-based) | Pip-installable, one-line API, no account/API key needed |
| Web/social search | **SerpApi — Google Lens / Reverse Image endpoint** (fallback: Bing Visual Search via Azure) | No GCP account needed (you said you don't have one). SerpApi signup is instant, has a free trial tier (100 searches/month free), and Google Lens results include direct visual matches with source page URLs — often *better* for face matches than Vision API's Web Detection, since Lens is Google's newer, more capable pipeline |
| Blockchain | Solidity contract on a **local Hardhat/Ganache-style chain via `eth-tester` + `web3.py`**, OR a locally-run **Ganache** instance | Zero faucet dependency = guaranteed to work in the recording. Task explicitly allows "local/simulated chain." Stretch goal: same contract redeployed to **Polygon Amoy testnet** if a funded wallet comes together in time |
| Demo interface | Single orchestrator Python script (`pipeline.py`) with clear stage-by-stage console output | No website needed per task rules; a clean, narrated terminal run is the fastest thing to build and the easiest thing to record |

**Consent note (keep doing this):** run the actual demo against your own face or a teammate's, with their OK. It's a stronger, cleaner demo anyway — you can show the real Instagram/LinkedIn post it finds without any consent ambiguity on camera.

---

## 1. Architecture

```
input_face.jpg
      │
      ▼
[Stage 1] Face Detection & Encoding  (face_recognition)
      │  → cropped face image, 128-d embedding
      ▼
[Stage 2] Web/Social Search          (SerpApi Google Lens)
      │  → list of candidate matching pages/images
      │  → filter for social domains, pick best real match
      ▼
[Stage 3] Fingerprinting             (hashlib SHA-256)
      │  → canonical JSON record {url, title, image_hash, face_hash, timestamp}
      │  → record_hash = sha256(canonical_json)
      ▼
[Stage 4] Blockchain Upload          (web3.py + Solidity contract)
      │  → addRecord(url, record_hash) tx on local/testnet chain
      │  → returns record_id + tx_hash
      ▼
[Stage 5] Re-Verification            (web3.py)
      │  → getRecord(record_id) from chain
      │  → recompute hash independently from original data
      │  → compare on-chain hash vs recomputed hash → PASS/FAIL
      ▼
   Console output + screen recording
```

---

## 2. Repo structure to create

```
face-blockchain-verify/
├── README.md
├── requirements.txt
├── .env.example
├── pipeline.py                  # single orchestrator script, run this end-to-end
├── src/
│   ├── face_stage.py            # Stage 1
│   ├── search_stage.py          # Stage 2
│   ├── fingerprint_stage.py     # Stage 3
│   ├── chain_client.py          # Stage 4 + 5 (web3.py wrapper)
│   └── config.py                # loads API keys, chain config from .env
├── contracts/
│   └── FaceVerification.sol
├── scripts/
│   ├── deploy_local.py          # compile+deploy to local chain, save address/ABI
│   └── deploy_testnet.py        # stretch goal: deploy to Polygon Amoy
├── sample_data/
│   └── input_face.jpg           # your own/consented test photo
└── recordings/
    └── (screen recording link goes in README, not the file itself)
```

---

## 3. Phase-by-phase build plan

### Phase 0 — Setup (30–45 min)
- [ ] `python -m venv venv && pip install face_recognition web3 py-solc-x requests python-dotenv`
  - Note: `face_recognition` needs `dlib` — on some machines this needs `cmake` + build tools preinstalled. If dlib install is painful on a teammate's machine, fall back to **`mediapipe`'s face detector + a simple embedding via `deepface`** (also pip-installable, no compiling).
- [ ] Sign up at serpapi.com → free API key (no credit card needed for trial tier).
- [ ] Install `ganache-cli` (`npm install -g ganache`) or use `eth-tester` (pure Python, no Node needed at all — **recommended** since you're avoiding a JS toolchain).
- [ ] Get 2–3 consented test photos with known public social presence (yourself/teammates) — this is your ground truth for "did it find a real match."

### Phase 1 — Face detection & encoding (2–3 hrs)
`src/face_stage.py`
- Load image, detect face bounding box, crop it, save as `face_crop.jpg`.
- Generate a 128-d encoding (used later just as part of the fingerprint payload, not for matching against the web — the web search step works on the *image*, not the raw encoding).
- Handle edge cases: no face found, multiple faces (pick largest bounding box).

### Phase 2 — Web/social search (3–5 hrs) — the trickiest stage, budget the most buffer here
`src/search_stage.py`
- Send `face_crop.jpg` to SerpApi's Google Lens endpoint (`engine=google_lens`), which accepts an image URL — so you'll need to briefly host the crop somewhere fetchable (a free tmp image host, or SerpApi's own upload support if available — check current docs, this detail can shift).
- Parse `visual_matches` results: each has a `link`, `title`, `source`.
- Filter/rank: prioritize results whose domain is a known social platform (`instagram.com`, `x.com`, `twitter.com`, `linkedin.com`, `facebook.com`, `reddit.com`, personal portfolio sites also acceptable as "social/web presence").
- Pick top real, live-fetchable result. **Do not hardcode a fallback URL** — if search genuinely finds nothing for the test photo on a given run, that's an honest result; swap to a photo you know has an indexed public presence.
- Fallback if SerpApi free tier gives you trouble mid-build: Bing Visual Search API (Azure, has its own free tier, no GCP needed either).

### Phase 3 — Fingerprinting (1 hr)
`src/fingerprint_stage.py`
- Build canonical record dict: `{source_url, page_title, matched_image_hash, face_crop_hash, timestamp}`.
- `record_hash = sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()`.
- Sort keys and fix formatting so re-verification later reproduces the identical hash.

### Phase 4 — Smart contract + local chain deploy (4–6 hrs)
`contracts/FaceVerification.sol` — minimal, gas-cheap:
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract FaceVerification {
    struct Record {
        string sourceUrl;
        string recordHash;
        uint256 timestamp;
        address submitter;
    }
    Record[] public records;

    event RecordAdded(uint256 indexed id, string recordHash, string sourceUrl);

    function addRecord(string memory _sourceUrl, string memory _recordHash) public returns (uint256) {
        records.push(Record(_sourceUrl, _recordHash, block.timestamp, msg.sender));
        uint256 id = records.length - 1;
        emit RecordAdded(id, _recordHash, _sourceUrl);
        return id;
    }

    function getRecord(uint256 id) public view returns (Record memory) {
        return records[id];
    }
}
```
- Compile with `py-solc-x` (pure Python, no Node/Hardhat needed).
- Deploy to an in-process `eth-tester` chain via `web3.py`'s `EthereumTesterProvider` — this gives you funded test accounts instantly, no faucet, no external process to keep alive during recording.
- `scripts/deploy_local.py` compiles, deploys, and writes `contract_address.json` + ABI for `chain_client.py` to reuse.
- **Stretch goal only, after core pipeline works:** `scripts/deploy_testnet.py` redeploys the same contract to Polygon Amoy (or Sepolia) using an RPC URL from Alchemy/Infura's free tier + a funded testnet wallet, for extra "real chain" credit in the recording.

### Phase 5 — Re-verification (1–2 hrs)
`src/chain_client.py`
- `get_record(record_id)` reads back the on-chain struct.
- Recompute the hash independently from the original `record` dict (not from anything cached from Stage 4).
- `assert onchain_hash == recomputed_hash` → print a clear ✅/❌ line. **This assertion + print is the single most important moment to show clearly in the recording.**

### Phase 6 — Orchestration (1–2 hrs)
`pipeline.py` — runs Stages 1→5 in order with clear, labeled console output at each step (e.g. `[1/5] Detecting face...`, `[2/5] Searching web for matches...`, etc.). This is what you'll actually run on camera.

### Phase 7 — README + cleanup (1 hr)
See section 5 below for the required README skeleton.

### Phase 8 — Screen recording (30–45 min)
Record: run `pipeline.py` start to finish, narrate each stage briefly, pause on the found social post (show it's a real, live URL — maybe open it in a browser tab briefly), and pause on the final verification PASS output.

---

## 4. Time budget summary (~26 hrs)

| Phase | Hours |
|---|---|
| 0. Setup | 0.5–0.75 |
| 1. Face detection | 2–3 |
| 2. Web search (buffer heavy) | 3–5 |
| 3. Fingerprinting | 1 |
| 4. Contract + chain | 4–6 |
| 5. Re-verification | 1–2 |
| 6. Orchestration | 1–2 |
| 7. README | 1 |
| 8. Recording | 0.5–0.75 |
| **Buffer for debugging** | **3–4** |
| **Total** | **~24–26 hrs** |

---

## 5. Required README skeleton

```markdown
# Face Identification & Blockchain Verification

## What this project does
[2-3 sentences: pipeline summary]

## Architecture
[reuse the diagram from section 1]

## How to run
1. Clone repo, `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, add your SerpApi key
3. `python scripts/deploy_local.py`  (deploys contract to local test chain)
4. `python pipeline.py --input sample_data/input_face.jpg`

## Which blockchain
Local Ethereum-compatible test chain via `eth-tester`/`web3.py` (chain ID, no external
node required). [If done: also deployed to Polygon Amoy testnet, contract address: 0x...]

## Known limitations
- Web search finds visually similar images, not cryptographically verified identity —
  a human should confirm the match is genuinely the same person.
- No liveness/anti-spoofing check on the input face scan.
- The blockchain record proves the fingerprint existed and is unaltered since upload —
  it does not itself prove the underlying face-to-post match was correct.
- Local chain is not persistent/public by default; see stretch-goal testnet deployment
  for a publicly verifiable record.
- SerpApi free tier is rate-limited; heavy repeated testing may need a paid key.

## Team / demo notes
Demo run against consented test photos (team members' own faces) only.
```

---

## 6. Risk list — check these first if something breaks late

1. **`dlib` fails to build** → switch to `mediapipe` + `deepface` (pure-pip, slower to install but no compiler needed).
2. **SerpApi free tier exhausted mid-testing** → switch to Bing Visual Search (Azure free tier) or Google Custom Search JSON API as a lower-fidelity fallback (returns similar images, not identity matches, but still a genuine search step).
3. **`eth-tester` version mismatch with `web3.py`** → pin versions in `requirements.txt` early (`web3==6.x`, `eth-tester` matching version) rather than debugging this the night before.
4. **No real match found for test photo** → don't hardcode a URL; instead pre-verify before recording day that your chosen test photo(s) actually return a hit, and keep 2–3 backup photos.

---

## 7. Submission checklist

- [ ] GitHub repo public, README complete per section 5
- [ ] `.env` / API keys **not** committed (`.gitignore` includes `.env`)
- [ ] Screen recording uploaded (YouTube unlisted / Drive / Loom), link works when tested in an incognito window
- [ ] Recording shows: face input → real search result → on-chain upload → re-verification pass, all in one continuous run
- [ ] Submission form filled: https://forms.gle/oZbQGuwiNeHVcHWo8
- [ ] Submitted before Sept 7, 11:59 PM — no resubmissions allowed, so do a final dry run before submitting

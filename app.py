#!/usr/bin/env python3
"""Flask Web UI for Face Identification & Blockchain Verification Pipeline."""

import hashlib
import json
import os
import sys
import time
import threading
import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, send_from_directory, stream_with_context

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max

# Store job status in memory
jobs = {}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def run_pipeline_job(job_id: str, image_path: str):
    job = jobs[job_id]
    job["status"] = "running"
    job["logs"] = []
    job["result"] = None
    job["error"] = None

    def emit(msg, level="info"):
        job["logs"].append({"msg": msg, "level": level, "ts": time.time()})

    try:
        import hashlib as _hashlib
        import json as _json

        emit("Pipeline started", "start")
        start_time = time.time()

        emit("[1/7] Face Detection & Encoding", "stage")
        from src.face_stage import detect_and_encode
        face_result = detect_and_encode(image_path, output_dir=app.config["UPLOAD_FOLDER"])
        emit(f"Detected {face_result.num_faces_detected} face(s)", "success")
        emit(f"Bounding box: {face_result.bbox}", "detail")
        emit(f"128-d encoding vector generated", "detail")
        job["face_crop"] = os.path.basename(face_result.face_crop_path)

        emit("[2/7] Local Face Database Lookup", "stage")
        from src import face_db
        db_match = face_db.lookup(face_result.encoding)

        identity_url = ""
        identity_title = ""
        identity_thumbnail = ""
        db_match_confidence = 0.0
        skip_web_search = False

        if db_match:
            emit(f"Match found in local database!", "success")
            emit(f"Identity: {db_match.name}", "detail")
            emit(f"URL: {db_match.url}", "detail")
            emit(f"Confidence: {db_match.confidence}%", "detail")
            identity_url = db_match.url
            identity_title = db_match.name
            db_match_confidence = db_match.confidence
            skip_web_search = True
        else:
            emit("No match in local database — proceeding to web search", "info")

        if not skip_web_search:
            emit("[3/7] Multi-Engine Web Search", "stage")
            emit("Querying Google Lens + Yandex reverse image search...", "info")
            from src.search_stage import search_and_verify
            search_result = search_and_verify(image_path, face_result.encoding)
            match = search_result.best_match

            if match:
                emit(f"Biometrically verified match found!", "success")
                emit(f"Title: {match.title}", "detail")
                emit(f"URL: {match.url}", "detail")
                emit(f"Engine: {match.engine}", "detail")
                emit(f"Face distance: {match.distance:.4f}", "detail")

                identity_url = match.url
                identity_title = match.title
                identity_thumbnail = match.thumbnail

                emit("Registering in local database...", "info")
                from src.face_db import config as db_config
                confidence = max(0.0, min(100.0, (1.0 - match.distance / db_config.FACE_MATCH_TOLERANCE) * 100.0))
                face_id = face_db.register(
                    encoding=face_result.encoding,
                    name=match.title,
                    url=match.url,
                    metadata={"engine": match.engine, "verified_confidence": confidence}
                )
                emit(f"Registered as DB ID #{face_id}", "detail")
            else:
                emit("No verified web match — registering as Unknown", "warn")
                next_id = face_db.get_next_unknown_id()
                unknown_name = f"Unknown #{next_id}"
                face_id = face_db.register(
                    encoding=face_result.encoding,
                    name=unknown_name,
                    url="",
                    metadata={"status": "unknown"}
                )
                identity_url = f"local://db/faces/{face_id}"
                identity_title = unknown_name

        emit("[5/7] Cryptographic Fingerprinting", "stage")
        from src.fingerprint_stage import create_fingerprint
        fp_result = create_fingerprint(
            source_url=identity_url,
            page_title=identity_title,
            face_crop_path=face_result.face_crop_path,
            face_encoding=face_result.encoding,
            matched_image_url=identity_thumbnail,
        )
        emit(f"SHA-256 fingerprint computed", "success")
        emit(f"Hash: {fp_result.record_hash[:32]}...", "detail")

        emit("[6/7] Blockchain Upload", "stage")
        emit("Connecting to Polygon Amoy Testnet...", "info")
        from src.chain_client import ChainClient
        chain = ChainClient()
        chain.setup_local_chain()
        emit(f"Wallet: {chain.account.address}", "detail")
        emit("Compiling & deploying FaceVerification smart contract...", "info")
        chain.deploy_contract()
        emit("Submitting verification record to Polygon Amoy blockchain...", "info")
        upload_result = chain.add_record(identity_url, fp_result.record_hash)
        emit(f"Record committed to Polygon Amoy blockchain!", "success")
        emit(f"Contract: {upload_result.contract_address}", "detail")
        emit(f"Record ID: #{upload_result.record_id}", "detail")
        emit(f"Tx hash: {upload_result.tx_hash[:40]}...", "detail")
        emit(f"Block: #{upload_result.block_number}", "detail")
        emit(f"Polygonscan: {upload_result.explorer_url}", "detail")

        emit("[7/7] On-Chain Re-Verification", "stage")
        emit("Re-computing hash independently from original data...", "info")
        recomputed_json = _json.dumps(fp_result.record, sort_keys=True, separators=(",", ":"))
        recomputed_hash = _hashlib.sha256(recomputed_json.encode("utf-8")).hexdigest()
        verification = chain.verify_record(upload_result.record_id, recomputed_hash)

        if verification.is_verified:
            emit("VERIFICATION PASSED — Record is authentic and untampered!", "success")
        else:
            emit("VERIFICATION FAILED — Hash mismatch detected!", "error")

        elapsed = time.time() - start_time

        if db_match_confidence > 0:
            match_source = f"Local Database ({db_match_confidence:.0f}% confidence)"
        elif "local://" in identity_url:
            match_source = "Unknown — No match found"
        else:
            match_source = "Web Search (Biometrically Verified)"

        job["result"] = {
            "identity": identity_title,
            "identity_url": identity_url,
            "match_source": match_source,
            "is_unknown": "local://" in identity_url,
            "record_hash": fp_result.record_hash,
            "tx_hash": upload_result.tx_hash,
            "contract_address": upload_result.contract_address,
            "record_id": upload_result.record_id,
            "block_number": upload_result.block_number,
            "explorer_url": upload_result.explorer_url,
            "is_verified": verification.is_verified,
            "elapsed": f"{elapsed:.1f}s",
            "faces_detected": face_result.num_faces_detected,
            "face_crop": job.get("face_crop", ""),
        }
        job["status"] = "done"
        emit(f"Pipeline complete in {elapsed:.1f}s", "start")

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        emit(f"Pipeline failed: {e}", "error")
        import traceback
        emit(traceback.format_exc(), "error")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    ext = Path(file.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        return jsonify({"error": "Only JPG/PNG/WEBP images are supported"}), 400

    job_id = str(uuid.uuid4())
    filename = f"{job_id}{ext}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    jobs[job_id] = {
        "status": "queued",
        "logs": [],
        "result": None,
        "error": None,
        "image": filename,
    }

    thread = threading.Thread(target=run_pipeline_job, args=(job_id, filepath), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        sent = 0
        while True:
            job = jobs[job_id]
            logs = job["logs"]
            while sent < len(logs):
                entry = logs[sent]
                yield f"data: {json.dumps(entry)}\n\n"
                sent += 1
            if job["status"] in ("done", "error"):
                final = {"msg": "__DONE__", "status": job["status"], "result": job.get("result"), "error": job.get("error")}
                yield f"data: {json.dumps(final)}\n\n"
                break
            time.sleep(0.2)

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/status/<job_id>")
def status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    job = jobs[job_id]
    return jsonify({"status": job["status"], "result": job.get("result"), "error": job.get("error")})


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)

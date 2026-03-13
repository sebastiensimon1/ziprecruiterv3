# app.py - ZipRecruiterV3 Flask API wrapper for Fly.io
# Exposes the SeleniumBase UC Driver scraper as an HTTP API.

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import time
import csv
import io
from datetime import datetime

from scraper import Ziprecruiter

app = Flask(__name__)
CORS(app)

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")
if not SCRAPER_API_KEY:
    raise RuntimeError("SCRAPER_API_KEY env var is not set — add it via: fly secrets set SCRAPER_API_KEY=...")


# ---------------------------------------------------------------------------
# Health / info routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "service": "ZipRecruiterV3 Scraper API",
        "version": "3.0.0 (SeleniumBase UC Driver)",
        "description": "Scrapes ZipRecruiter jobs via SeleniumBase undetected Chrome",
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200


# ---------------------------------------------------------------------------
# Main scrape endpoint
# ---------------------------------------------------------------------------

@app.route("/scrape", methods=["POST"])
def scrape():
    try:
        # Auth
        api_key = request.headers.get("X-API-Key") or (request.json or {}).get("api_key")
        if api_key != SCRAPER_API_KEY:
            return jsonify({"success": False, "error": "Invalid API key"}), 401

        data          = request.json or {}
        search_term   = data.get("keyword", "").strip()
        max_jobs      = data.get("results")
        if max_jobs is not None:
            max_jobs = min(int(max_jobs), 200)
        remote_only   = bool(data.get("remote_only", True))
        zip_apply_only = bool(data.get("zip_apply_only", False))
        start_page    = int(data.get("start_page", 0))

        if not search_term:
            return jsonify({"success": False, "error": "keyword is required"}), 400

        mode_of_work = "remote" if remote_only else None

        print(f"[API] /scrape — keyword='{search_term}', results={max_jobs}, "
              f"remote_only={remote_only}, zip_apply_only={zip_apply_only}")

        scraper = Ziprecruiter(
            headless=True,
            except_titles=True,
            exclude_easy_apply=True,
            remote_only=remote_only,
        )

        start = time.time()

        # Use in-memory output path (temp file in /tmp)
        tmp_file = f"/tmp/zr_{search_term.replace(' ', '_')}_{int(start)}.csv"

        jobs = scraper.scraper_zip_recruiter(
            search=search_term,
            location="USA",
            zip_apply_only=zip_apply_only,
            mode_of_work=mode_of_work,
            radius=5000,
            days=None,
            min_salary=None,
            max_salary=None,
            employment_type="full_time",
            experience_level=None,
            max_jobs=max_jobs,
            start_page=start_page,
            output_file=tmp_file,
        )

        elapsed = round(time.time() - start, 2)

        # Clean up temp file
        try:
            os.remove(tmp_file)
        except Exception:
            pass

        return jsonify({
            "success": True,
            "count": len(jobs),
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
            "jobs": jobs,
        })

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[STARTUP] ZipRecruiterV3 API listening on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

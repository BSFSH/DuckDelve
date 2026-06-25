# --- imports (top of file) ---
import os
import logging
from datetime import timedelta
from typing import Any, Dict

from flask import Flask, request, jsonify, render_template, session
from flask_session import Session  # server-side sessions

import sheets
from parsing import parse
from matching import match_all

# --- app + secrets ---
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-please-change")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=6)

# --- SERVER-SIDE SESSIONS (filesystem) ---
SESSION_DIR = os.path.expanduser("~/.flask_session")
os.makedirs(SESSION_DIR, mode=0o700, exist_ok=True)  # ensure it exists & is private

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = SESSION_DIR
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_COOKIE_SECURE"] = True      # HTTPS on PythonAnywhere
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"   # or "Strict" if you prefer

Session(app)  # initialize Flask-Session

# --- logging (helps diagnose 502s) ---
LOG_PATH = os.path.expanduser("~/DuckDelve/flask.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Core lookup
# ------------------------------------------------------------------------------
def _lookup_and_cache(raw_text: str) -> Dict[str, Any]:
    """
    Parse the pasted text, resolve each item against the gear + craft-mats sheets,
    cache the matched gear in the session, and return the front-end payload.
    """
    parsed = parse(raw_text)
    main_data = sheets.get_items_from_sheet()
    craft_data = sheets.get_craft_mats_from_sheet()

    result = match_all(parsed, main_data, craft_data)

    session.permanent = True
    session["delved_items"] = result.items

    return {
        "ok": True,
        "count": len(result.items),
        "headers": result.headers,
        "items": result.items,
        "craft_headers": result.craft_headers,
        "craft_items": result.craft_items,
        "not_found": result.not_found,
        "not_found_detailed": result.not_found_detailed,
    }


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/items")
def api_items():
    """Structured JSON lookup."""
    try:
        payload = request.get_json(silent=True) or {}
        raw_text = payload.get("input", "") or payload.get("items", "")
        return jsonify(_lookup_and_cache(raw_text)), 200
    except Exception as e:
        logger.exception("/api/items failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/submit")
def submit():
    """
    Compatibility route for the existing front-end.
    Always returns JSON (even on error) so the UI doesn't crash on HTML.
    """
    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
            raw_text = data.get("items", "") or data.get("input", "") or ""
        else:
            raw_text = (
                request.form.get("items")
                or request.form.get("input")
                or request.form.get("text")
                or ""
            )
        return jsonify(_lookup_and_cache(raw_text)), 200
    except Exception as e:
        logger.exception("/submit failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ----------------------- Session-backed edit endpoints -------------------------
@app.get("/session/items")
def get_session_items():
    return jsonify(session.get("delved_items", []))


@app.post("/session/items/patch")
def patch_session_items():
    data = request.get_json(force=True) or {}
    idx = data.get("index")
    changes = data.get("changes", {})
    if not isinstance(idx, int):
        return jsonify({"error": "index must be an integer"}), 400
    if not isinstance(changes, dict):
        return jsonify({"error": "changes must be an object"}), 400

    items = session.get("delved_items", [])
    if not (0 <= idx < len(items)):
        return jsonify({"error": "index out of range"}), 400

    items[idx].update(changes)
    session["delved_items"] = items
    return jsonify({"ok": True, "index": idx, "item": items[idx]})


@app.post("/session/items/replace")
def replace_session_items():
    data = request.get_json(force=True) or {}
    items = data.get("items")
    if not isinstance(items, list):
        return jsonify({"error": "items must be a list"}), 400
    if not all(isinstance(x, dict) for x in items):
        return jsonify({"error": "each item must be an object"}), 400
    session["delved_items"] = items
    return jsonify({"ok": True, "count": len(items)})


@app.post("/session/items/clear")
def clear_session_items():
    session.pop("delved_items", None)
    return jsonify({"ok": True})


# ------------------------------------------------------------------------------
# Health
# ------------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})


# ------------------------------------------------------------------------------
# Entrypoint (dev only)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # For local debugging only; on PythonAnywhere the WSGI server runs this app.
    app.run(host="0.0.0.0", port=5000, debug=True)

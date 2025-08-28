# --- imports (top of file) ---
import os
import re
import csv
import io
import logging
from datetime import timedelta
from typing import List, Optional, Dict, Any, Tuple

import requests
from flask import Flask, request, jsonify, render_template, session
from flask_session import Session  # server-side sessions

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
# Data source
# ------------------------------------------------------------------------------
CSV_URL = (
    "https://docs.google.com/spreadsheets/d/1Jw5W_0jCDGE26IsnFV0nwV6DOQDGGigp/"
    "export?format=csv&gid=204162352"
)

def _download_csv(url: str, timeout: int = 25) -> str:
    """
    Robust downloader for Google CSV exports.
    - follows redirects
    - raises for HTTP errors
    - verifies we didn't get an HTML page
    - strips NULs that break csv module
    """
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.exception("CSV download failed")
        raise

    ctype = (resp.headers.get("Content-Type") or "").lower()
    text = resp.content.decode("utf-8", errors="replace").replace("\x00", "")

    # Sometimes Google sends CSV with octet-stream; allow that.
    if "text/html" in ctype or text.lstrip().startswith("<!DOCTYPE"):
        logger.error("Expected CSV but received HTML. Check sharing/export URL.")
        raise ValueError("Expected CSV but received HTML")

    return text

def get_items_from_sheet() -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Fetch the Google Sheet CSV and return (headers, rows_as_dicts).
    Also writes a snapshot to 'parsed_google_sheet.csv' for debugging.
    """
    csv_text = _download_csv(CSV_URL)
    reader = csv.reader(io.StringIO(csv_text, newline=""))
    rows = list(reader)

    # Save a local snapshot to inspect if needed
    try:
        with open("parsed_google_sheet.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
    except Exception:
        logger.warning("Could not write parsed_google_sheet.csv", exc_info=True)

    if not rows:
        logger.error("CSV appears empty")
        return [], []

    headers = rows[0]
    data_rows = rows[1:]

    dict_rows: List[Dict[str, Any]] = []
    for r in data_rows:
        # pad/truncate to header length
        padded = (r + [""] * len(headers))[: len(headers)]
        dict_rows.append({h: v for h, v in zip(headers, padded)})

    return headers, dict_rows


# ------------------------------------------------------------------------------
# Input sanitation
# ------------------------------------------------------------------------------
ARTICLES = ("a ", "an ", "the ")
ENCHANT_PREFIXES = (
    "brilliant ",
    "lustrous ",
    "glowing ",
    "shining ",
    "bright ",
    "silvered ",
)
MATERIAL_PREFIXES = (
    "bronze ",
    "iron ",
    "steel ",
    "alloy ",
    "mithril ",
    "laen ",
    "wool ",
    "cotton ",
    "silk ",
    "gossamer ",
    "wispweave ",
    "ebonweave ",
    "leather ",
    "rough ",
    "embossed ",
    "suede ",
    "wyvern scale ",
    "enchanted ",
    "maple ",
    "oak ",
    "yew ",
    "rosewood ",
    "ironwood ",
    "ebony ",
)
UNWANTED_PREFIXES = ("(w) ", "(h) ")
SUFFIX_TO_REMOVE = " is here."
PHRASES_TO_REMOVE = ("you also see",)  # case-insensitive
AND_A_PATTERN = re.compile(r"\band a\b", re.IGNORECASE)

LEADING_ENUM_OR_BULLET = re.compile(
    r"^\s*(?:\d+\s*\)|\d+\s*\.\)|\d+\s*\.\s*|[-+*•]\s+)\s*"
)
SURROUNDING_QUOTES = re.compile(r'^\s*[\'"]?(.*?)[\'"]?\s*$')
LEADING_ARTICLES_RE = re.compile(r"^\s*(?:a|an|the)\s+", re.IGNORECASE)

def _normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def _strip_prefix_loop(s: str, prefixes: tuple) -> str:
    lowered = s.lower()
    changed = True
    while changed:
        changed = False
        for p in prefixes:
            if lowered.startswith(p):
                s = s[len(p) :]
                lowered = lowered[len(p) :]
                changed = True
                break
    return s

def sanitize_input(raw_text: str) -> List[str]:
    """
    Full sanitizer with original behaviors + robustness.
    """
    if not raw_text:
        return []

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    for phrase in PHRASES_TO_REMOVE:
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)

    text = AND_A_PATTERN.sub(" ", text)

    parts = re.split(r"[,\n]+", text)

    cleaned: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue

        if ":" in p:
            p = p.split(":")[-1].strip()

        p = LEADING_ENUM_OR_BULLET.sub("", p)

        p_lower = p.lower()
        for uw in UNWANTED_PREFIXES:
            if p_lower.startswith(uw):
                p = p[len(uw) :]
                p_lower = p.lower()

        m = SURROUNDING_QUOTES.match(p)
        if m:
            p = m.group(1)

        p = LEADING_ARTICLES_RE.sub("", p).strip()

        p = _strip_prefix_loop(p, tuple(s.lower() for s in ENCHANT_PREFIXES))
        p = _strip_prefix_loop(p, tuple(s.lower() for s in MATERIAL_PREFIXES))

        if p.lower().endswith(SUFFIX_TO_REMOVE):
            p = p[: -len(SUFFIX_TO_REMOVE)]

        p = _normalize_spaces(p)

        if p:
            cleaned.append(p)

    return cleaned


# ------------------------------------------------------------------------------
# Matching helpers
# ------------------------------------------------------------------------------
def _detect_item_col(headers: List[str]) -> Optional[int]:
    for i, h in enumerate(headers):
        if h.strip().lower() in ("item", "name", "item name"):
            return i
    return None

def _row_matches_term(row_dict: Dict[str, Any], term_lower: str) -> bool:
    for v in row_dict.values():
        if term_lower in str(v).lower():
            return True
    return False

def _find_matches(
    headers: List[str], rows: List[Dict[str, Any]], terms: List[str]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Returns (matches, not_found_terms).
    """
    matches: List[Dict[str, Any]] = []
    not_found: List[str] = []
    item_col_idx = _detect_item_col(headers)
    terms_lower = [t.lower() for t in terms]

    for t in terms_lower:
        term_matches: List[Dict[str, Any]] = []
        if item_col_idx is not None:
            col_name = headers[item_col_idx]
            # exact
            for r in rows:
                candidate = str(r.get(col_name, "")).strip().lower()
                if candidate == t:
                    term_matches.append(r)
            # startswith
            if not term_matches:
                for r in rows:
                    candidate = str(r.get(col_name, "")).strip().lower()
                    if candidate.startswith(t):
                        term_matches.append(r)
            # contains
            if not term_matches:
                for r in rows:
                    candidate = str(r.get(col_name, "")).strip().lower()
                    if t in candidate:
                        term_matches.append(r)
        else:
            for r in rows:
                if _row_matches_term(r, t):
                    term_matches.append(r)

        if term_matches:
            matches.extend(term_matches)
        else:
            not_found.append(t)

    return matches, not_found

def _lookup_and_cache(raw_text: str) -> Dict[str, Any]:
    """
    - sanitize
    - fetch sheet
    - find matches (and not_found list)
    - cache items in session
    - return structured payload for the front-end
    """
    terms = sanitize_input(raw_text)
    headers, rows = get_items_from_sheet()
    matched, not_found = _find_matches(headers, rows, terms)

    session.permanent = True
    session["delved_items"] = matched

    return {
        "ok": True,
        "count": len(matched),
        "headers": headers,
        "items": matched,
        "not_found": not_found,
    }


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.post("/api/items")
def api_items():
    """
    Structured JSON: {"ok", "count", "headers", "items", "not_found"}.
    """
    try:
        payload = request.get_json(silent=True) or {}
        raw_text = payload.get("input", "") or payload.get("items", "")
        result = _lookup_and_cache(raw_text)
        return jsonify(result), 200
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
        result = _lookup_and_cache(raw_text)
        return jsonify(result), 200
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


# ---------------------- Sets endpoints (combinatorics) ------------------------
@app.get("/sets/current")
def sets_current():
    items = session.get("delved_items", [])
    if not items:
        return jsonify({"ok": True, "sets_count": 0})
    total = sum(1 for _ in generate_armor_combinations(items))
    return jsonify({"ok": True, "sets_count": total})

@app.post("/sets/filter")
def sets_filter():
    payload = request.get_json(silent=True) or {}
    spells = payload.get("spells", [])
    if isinstance(spells, str):
        spells = [spells]
    spells = [str(s or "").strip().lower() for s in spells if str(s or "").strip()]

    items = session.get("delved_items", [])
    if not items:
        return jsonify({"ok": True, "sets_count": 0})

    combos = generate_armor_combinations(items)
    filtered = filter_combinations_by_spells(
        combos, spells, mode="all", field="Spell", lowercase=True
    )
    return jsonify({"ok": True, "sets_count": len(filtered)})


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

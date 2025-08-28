# app.py
import csv
import re
import requests
from io import StringIO
from datetime import timedelta

from flask import Flask, request, jsonify, render_template, session
from flask_session import Session
from archive.armor_combos import generate_armor_combinations, filter_combinations_by_spells

app = Flask(__name__)

# ------------------------------------------------------------------------------
# App / Session config
# ------------------------------------------------------------------------------
app.config['SECRET_KEY'] = 'change-me-to-a-long-random-string'  # change in prod
app.config['SESSION_TYPE'] = 'filesystem'           # simplest for dev
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=6)
Session(app)

# ------------------------------------------------------------------------------
# Data source
# ------------------------------------------------------------------------------
CSV_URL = 'https://docs.google.com/spreadsheets/d/1Jw5W_0jCDGE26IsnFV0nwV6DOQDGGigp/export?format=csv&gid=204162352'


def get_items_from_sheet():
    """
    Fetch the Google Sheet CSV and return (headers, rows_as_dicts).
    Also writes a snapshot to 'parsed_google_sheet.csv' for debugging.
    """
    resp = requests.get(CSV_URL, timeout=30)
    resp.raise_for_status()
    csv_text = resp.text

    reader = csv.reader(StringIO(csv_text))
    rows = list(reader)

    # Local snapshot for debugging
    with open('parsed_google_sheet.csv', 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows(rows)

    if not rows:
        return [], []

    headers = rows[0]
    data_rows = rows[1:]

    dict_rows = []
    for r in data_rows:
        padded = (r + [""] * len(headers))[:len(headers)]
        dict_rows.append({h: v for h, v in zip(headers, padded)})

    return headers, dict_rows

# ------------------------------------------------------------------------------
# Input sanitation
# ------------------------------------------------------------------------------
# Original semantics you listed (plus earlier rules we've been using):
ARTICLES = ("a ", "an ", "the ")
ENCHANT_PREFIXES = (
    "brilliant ", "lustrous ", "glowing ", "shining ", "bright ", "silvered "
)
MATERIAL_PREFIXES = (
    "bronze ", "iron ", "steel ", "alloy ", "mithril ", "laen ",
    "wool ", "cotton ", "silk ", "gossamer ", "wispweave ", "ebonweave ",
    "leather ", "rough ", "embossed ", "suede ", "wyvern scale ", "enchanted ",
    "maple ", "oak ", "yew ", "rosewood ", "ironwood ", "ebony "
)
UNWANTED_PREFIXES = ("(w) ", "(h) ")
SUFFIX_TO_REMOVE = " is here."
PHRASES_TO_REMOVE = ("you also see",)  # case-insensitive
AND_A_PATTERN = re.compile(r'\band a\b', re.IGNORECASE)

# Additional robustness so your numbered/bulleted paste still works:
LEADING_ENUM_OR_BULLET = re.compile(
    r'^\s*(?:\d+\s*\)|\d+\s*\.\)|\d+\s*\.\s*|[-+*•]\s+)\s*'
)
SURROUNDING_QUOTES = re.compile(r'^\s*[\'"]?(.*?)[\'"]?\s*$')
LEADING_ARTICLES_RE = re.compile(r'^\s*(?:a|an|the)\s+', re.IGNORECASE)

def _normalize_spaces(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()

def _strip_prefix_loop(s: str, prefixes: tuple) -> str:
    """
    Repeatedly strip any of the provided prefixes from the very start of s,
    case-insensitive. Stops when none match.
    """
    lowered = s.lower()
    changed = True
    while changed:
        changed = False
        for p in prefixes:
            if lowered.startswith(p):
                s = s[len(p):]
                lowered = lowered[len(p):]
                changed = True
                break
    return s

def sanitize_input(raw_text: str) -> list[str]:
    """
    Full sanitizer with ALL original behaviors + robustness:

    - Split on commas and newlines.
    - Remove 'You also see' (case-insensitive).
    - Remove 'and a' phrase (case-insensitive).
    - Keep only the text to the RIGHT of the last colon (if present).
    - Strip leading enumeration/bullets like '67.) ', '-', '•'.
    - Remove UNWANTED_PREFIXES: '(w) ', '(h) '.
    - Remove surrounding quotes.
    - Remove leading articles 'a ', 'an ', 'the ' (repeat once at start).
    - Remove ENCHANT_PREFIXES and MATERIAL_PREFIXES (repeat until gone).
    - Remove trailing ' is here.' if present.
    - Collapse internal whitespace and drop empties.
    """
    if not raw_text:
        return []

    # Normalize line breaks
    text = raw_text.replace('\r\n', '\n').replace('\r', '\n')

    # Remove phrases
    for phrase in PHRASES_TO_REMOVE:
        text = re.sub(re.escape(phrase), ' ', text, flags=re.IGNORECASE)

    # Remove 'and a' connector (it often glues list fragments)
    text = AND_A_PATTERN.sub(' ', text)

    # Split on commas OR newlines
    parts = re.split(r'[,\n]+', text)

    cleaned: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue

        # If there are colons, keep only the right-most side
        if ':' in p:
            p = p.split(':')[-1].strip()

        # Remove leading enumerations/bullets like "67.) " or "- "
        p = LEADING_ENUM_OR_BULLET.sub('', p)

        # Remove unwanted "(w) " / "(h) " etc.
        p_lower = p.lower()
        for uw in UNWANTED_PREFIXES:
            if p_lower.startswith(uw):
                p = p[len(uw):]
                p_lower = p.lower()

        # Remove surrounding quotes
        m = SURROUNDING_QUOTES.match(p)
        if m:
            p = m.group(1)

        # Remove leading articles (once at the very start)
        p = LEADING_ARTICLES_RE.sub('', p).strip()

        # Remove enchant/material prefixes repeatedly at the very start
        p = _strip_prefix_loop(p, tuple(s.lower() for s in ENCHANT_PREFIXES))
        p = _strip_prefix_loop(p, tuple(s.lower() for s in MATERIAL_PREFIXES))

        # Remove trailing ' is here.'
        if p.lower().endswith(SUFFIX_TO_REMOVE):
            p = p[:-len(SUFFIX_TO_REMOVE)]

        # Normalize internal whitespace
        p = _normalize_spaces(p)

        if p:
            cleaned.append(p)

    return cleaned

# ------------------------------------------------------------------------------
# Matching helpers
# ------------------------------------------------------------------------------
def _detect_item_col(headers: list[str]) -> int | None:
    for i, h in enumerate(headers):
        if h.strip().lower() in ('item', 'name', 'item name'):
            return i
    return None

def _row_matches_term(row_dict: dict, term_lower: str) -> bool:
    for v in row_dict.values():
        if term_lower in str(v).lower():
            return True
    return False

def _find_matches(headers: list[str], rows: list[dict], terms: list[str]) -> tuple[list[dict], list[str]]:
    """
    Returns (matches, not_found_terms).
    """
    matches: list[dict] = []
    not_found: list[str] = []
    item_col_idx = _detect_item_col(headers)
    terms_lower = [t.lower() for t in terms]

    for t in terms_lower:
        term_matches: list[dict] = []
        if item_col_idx is not None:
            col_name = headers[item_col_idx]
            # exact
            for r in rows:
                candidate = str(r.get(col_name, '')).strip().lower()
                if candidate == t:
                    term_matches.append(r)
            # startswith
            if not term_matches:
                for r in rows:
                    candidate = str(r.get(col_name, '')).strip().lower()
                    if candidate.startswith(t):
                        term_matches.append(r)
            # contains
            if not term_matches:
                for r in rows:
                    candidate = str(r.get(col_name, '')).strip().lower()
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

def _lookup_and_cache(raw_text: str) -> dict:
    """
    - sanitize
    - fetch sheet
    - find matches (and not_found list)
    - cache items in session
    - return structured payload that your front-end expects
    """
    terms = sanitize_input(raw_text)
    headers, rows = get_items_from_sheet()
    matched, not_found = _find_matches(headers, rows, terms)

    session.permanent = True
    session['delved_items'] = matched

    return {
        "count": len(matched),
        "headers": headers,
        "items": matched,
        "not_found": not_found
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
    Structured JSON: {"count", "headers", "items", "not_found"}.
    """
    payload = request.get_json(silent=True) or {}
    raw_text = payload.get("input", "") or payload.get("items", "")
    result = _lookup_and_cache(raw_text)
    return jsonify(result)

@app.post("/submit")
def submit():
    """
    Compatibility route for the existing front-end.
    Returns the same structured object your script.js expects.
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
        raw_text = data.get("items", "") or data.get("input", "") or ""
    else:
        raw_text = request.form.get("items") or request.form.get("input") or request.form.get("text") or ""

    result = _lookup_and_cache(raw_text)
    return jsonify(result)

# --------------------- Session-backed edit endpoints --------------------------
@app.get("/session/items")
def get_session_items():
    return jsonify(session.get('delved_items', []))

@app.post("/session/items/patch")
def patch_session_items():
    data = request.get_json(force=True) or {}
    idx = data.get("index")
    changes = data.get("changes", {})
    if not isinstance(idx, int):
        return jsonify({"error": "index must be an integer"}), 400
    if not isinstance(changes, dict):
        return jsonify({"error": "changes must be an object"}), 400

    items = session.get('delved_items', [])
    if not (0 <= idx < len(items)):
        return jsonify({"error": "index out of range"}), 400

    items[idx].update(changes)
    session['delved_items'] = items
    return jsonify({"ok": True, "index": idx, "item": items[idx]})

@app.post("/session/items/replace")
def replace_session_items():
    data = request.get_json(force=True) or {}
    items = data.get("items")
    if not isinstance(items, list):
        return jsonify({"error": "items must be a list"}), 400
    if not all(isinstance(x, dict) for x in items):
        return jsonify({"error": "each item must be an object"}), 400
    session['delved_items'] = items
    return jsonify({"ok": True, "count": len(items)})

@app.post("/session/items/clear")
def clear_session_items():
    session.pop('delved_items', None)
    return jsonify({"ok": True})

# ---------------------- NEW: sets count from session --------------------------
@app.get("/sets/current")
def sets_current():
    """
    Compute the number of valid armor combinations from the most recent
    delved items in the session (no filters; 6 armor slots + 2 distinct jewels).
    """
    items = session.get("delved_items", [])
    if not items:
        return jsonify({"ok": True, "sets_count": 0})

    # Count exactly using your generator (same rules as the backend combos)
    total = sum(1 for _ in generate_armor_combinations(items))
    return jsonify({"ok": True, "sets_count": total})

@app.post("/sets/filter")
def sets_filter():
    """
    Count valid combinations that include ALL selected spells.
    JSON body: { "spells": ["dexterity.ii", "agility.ii", ...] }
    """
    payload = request.get_json(silent=True) or {}
    spells = payload.get("spells", [])
    if isinstance(spells, str):
        spells = [spells]
    # normalize and drop empties
    spells = [str(s or "").strip().lower() for s in spells if str(s or "").strip()]

    items = session.get("delved_items", [])
    if not items:
        return jsonify({"ok": True, "sets_count": 0})

    combos = generate_armor_combinations(items)
    filtered = filter_combinations_by_spells(combos, spells, mode="all", field="Spell", lowercase=True)
    return jsonify({"ok": True, "sets_count": len(filtered)})

# ------------------------------------------------------------------------------
# Health
# ------------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})

# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

"""
Google Sheet data source for DuckDelve.

Fetches the item sheets (main gear tab + craft-mats tab) as CSV, parses them into
header/row-dict pairs, and caches the result in-memory with a short TTL so a delve
doesn't re-download the whole sheet on every submit.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import threading
import time
from typing import Any, Dict, List, Tuple

import requests

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Sheet identifiers
# ------------------------------------------------------------------------------
SHEET_DOC_ID = "1hvdRBDD8bOtEVLI7rPGz0ZMzDm5_5cuX"
MAIN_GID = "204162352"       # gear / items tab
CRAFT_GID = "1709215391"     # crafting materials tab

# Local snapshot of the main tab, written on a real fetch for debugging.
SNAPSHOT_PATH = "parsed_google_sheet.csv"

# In-memory cache lifetime (seconds). A delve within this window is served from
# memory instead of re-downloading. First request after expiry refetches.
CACHE_TTL = 600

# Result type: (headers, rows_as_dicts)
SheetData = Tuple[List[str], List[Dict[str, Any]]]

# gid -> (fetched_at_epoch, SheetData)
_cache: Dict[str, Tuple[float, SheetData]] = {}
_cache_lock = threading.RLock()


def _export_url(gid: str) -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{SHEET_DOC_ID}/"
        f"export?format=csv&gid={gid}"
    )


def _download_csv(url: str, timeout: int = 25) -> str:
    """
    Robust downloader for Google CSV exports.
    - follows redirects
    - raises for HTTP errors
    - verifies we didn't get an HTML page
    - strips NULs that break the csv module
    """
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception("CSV download failed")
        raise

    ctype = (resp.headers.get("Content-Type") or "").lower()
    text = resp.content.decode("utf-8", errors="replace").replace("\x00", "")

    # Sometimes Google sends CSV with octet-stream; allow that, but reject HTML.
    if "text/html" in ctype or text.lstrip().startswith("<!DOCTYPE"):
        logger.error("Expected CSV but received HTML. Check sharing/export URL.")
        raise ValueError("Expected CSV but received HTML")

    return text


def _csv_to_records(csv_text: str) -> SheetData:
    """Parse CSV text into (headers, list of row dicts keyed by header)."""
    reader = csv.reader(io.StringIO(csv_text, newline=""))
    rows = list(reader)
    if not rows:
        logger.error("CSV appears empty")
        return [], []

    headers = rows[0]
    dict_rows: List[Dict[str, Any]] = []
    for r in rows[1:]:
        padded = (r + [""] * len(headers))[: len(headers)]
        dict_rows.append({h: v for h, v in zip(headers, padded)})

    return headers, dict_rows


def _write_snapshot(csv_text: str) -> None:
    try:
        with open(SNAPSHOT_PATH, "w", newline="", encoding="utf-8") as f:
            f.write(csv_text)
    except Exception:
        logger.warning("Could not write %s", SNAPSHOT_PATH, exc_info=True)


def fetch_sheet(gid: str, *, force: bool = False) -> SheetData:
    """
    Return (headers, rows) for a sheet tab, served from the in-memory TTL cache
    when fresh. Pass force=True to bypass the cache and re-download.

    The main tab's raw CSV is also written to SNAPSHOT_PATH on a real fetch.
    """
    now = time.time()
    with _cache_lock:
        cached = _cache.get(gid)
        if cached and not force and (now - cached[0]) < CACHE_TTL:
            return cached[1]

    # Network fetch outside the lock so concurrent requests don't serialize on it.
    csv_text = _download_csv(_export_url(gid))
    if gid == MAIN_GID:
        _write_snapshot(csv_text)
    data = _csv_to_records(csv_text)

    with _cache_lock:
        _cache[gid] = (time.time(), data)
    return data


def clear_cache() -> None:
    """Drop all cached sheet data (used by tests / a future manual refresh)."""
    with _cache_lock:
        _cache.clear()


# Backwards-compatible convenience wrappers ------------------------------------
def get_items_from_sheet(*, force: bool = False) -> SheetData:
    """Main gear/items tab."""
    return fetch_sheet(MAIN_GID, force=force)


def get_craft_mats_from_sheet(*, force: bool = False) -> SheetData:
    """Crafting materials tab."""
    return fetch_sheet(CRAFT_GID, force=force)

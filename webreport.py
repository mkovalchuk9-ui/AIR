"""
Writes the day's flagged artists to docs/data/latest.json — a static file
that the GitHub Pages site (docs/index.html) fetches at page load. No
server, database, or email needed; GitHub Pages just serves the JSON as a
static asset, updated by the same Actions job that runs the scan.

Also appends a lightweight entry to docs/data/runs.json (date + count) so
the page can show a small "last few days" trend without needing full history.
"""

import json
import os
import logging
from datetime import datetime, timezone

from analyzer import Flagged

logger = logging.getLogger("tiktok_scout.webreport")

DOCS_DATA_DIR = "docs/data"
LATEST_PATH = os.path.join(DOCS_DATA_DIR, "latest.json")
RUNS_PATH = os.path.join(DOCS_DATA_DIR, "runs.json")
MAX_RUNS_KEPT = 30


def _flagged_to_dict(f: Flagged) -> dict:
    return {
        "handle": f.creator_handle,
        "displayName": f.creator_display_name,
        "videoUrl": f.video_url,
        "caption": f.caption_text,
        "views": f.view_count,
        "baselineAvg": f.baseline_avg,
        "multiple": f.multiple,
        "genre": f.genre_tag,
        "market": f.market,
        "unsignedConfidence": f.unsigned_confidence,
    }


def write(flagged: list[Flagged], market_scope: str = "US") -> None:
    os.makedirs(DOCS_DATA_DIR, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    latest = {
        "generatedAt": now,
        "marketScope": market_scope,
        "count": len(flagged),
        "artists": [_flagged_to_dict(f) for f in flagged],
    }
    with open(LATEST_PATH, "w") as f:
        json.dump(latest, f, indent=2)
    logger.info("Wrote %s (%d flagged)", LATEST_PATH, len(flagged))

    runs = []
    if os.path.exists(RUNS_PATH):
        try:
            with open(RUNS_PATH) as f:
                runs = json.load(f)
        except (json.JSONDecodeError, OSError):
            runs = []

    runs.append({"date": now, "count": len(flagged)})
    runs = runs[-MAX_RUNS_KEPT:]

    with open(RUNS_PATH, "w") as f:
        json.dump(runs, f, indent=2)
    logger.info("Updated %s (%d entries kept)", RUNS_PATH, len(runs))

"""
Lightweight SQLite storage so we can build up a per-artist view-count
history over time (needed to detect "higher than normal" spikes).
The db file itself is committed back to the repo by the GitHub Actions
workflow after each run, so history persists across daily runs.
"""

import sqlite3
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS video_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_handle TEXT NOT NULL,
    video_url TEXT,
    view_count INTEGER,
    caption_text TEXT,
    bio_text TEXT,
    genre_tag TEXT,
    market TEXT,
    posted_at INTEGER,
    observed_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_creator ON video_observations (creator_handle);
"""


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.executescript(SCHEMA)

    # Migration for databases created before posted_at existed (yours,
    # from earlier runs, is one of these) — add the column if missing
    # rather than requiring a fresh database.
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(video_observations)")}
    if "posted_at" not in existing_cols:
        conn.execute("ALTER TABLE video_observations ADD COLUMN posted_at INTEGER")
        conn.commit()

    return conn


def parse_post_date(post_date_text: Optional[str]) -> Optional[int]:
    """
    Parse Apify's createTimeISO (e.g. "2026-08-21T14:32:10.000Z") into a
    unix timestamp. Returns None if missing or unparseable — callers should
    treat unknown post dates cautiously (see analyzer.py), not assume recency.
    """
    if not post_date_text:
        return None
    try:
        cleaned = post_date_text.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None


def record_observation(conn: sqlite3.Connection, video: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO video_observations
            (creator_handle, video_url, view_count, caption_text, bio_text,
             genre_tag, market, posted_at, observed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            video.get("creator_handle"),
            video.get("video_url"),
            video.get("view_count"),
            video.get("caption_text"),
            video.get("bio_text"),
            video.get("_genre_tag"),
            video.get("_market"),
            parse_post_date(video.get("post_date_text")),
            int(time.time()),
        ),
    )


def get_artist_history(
    conn: sqlite3.Connection, creator_handle: str, before_timestamp: int
) -> list[int]:
    """
    Return this artist's view counts recorded strictly BEFORE before_timestamp
    — i.e. from prior runs, not from videos discovered in the current run.

    This used to exclude by matching video_url instead, which was a bug:
    an artist whose same video keeps reappearing under a hashtag day after
    day would have every historical row filtered out (since it always
    matched "the same video"), meaning they could never build history no
    matter how many days passed. Cutting off by timestamp instead means a
    slow-growing recurring video correctly compares against its own past
    readings (usually ~1x, no false spike), while a genuinely new video
    compares against the artist's prior distinct videos.

    This also fixes a same-run contamination bug: a creator can appear
    under multiple different hashtags in one run, producing several rows
    with the same observed_at. Those siblings shouldn't count as "history"
    for each other, and the timestamp cutoff naturally excludes them since
    they're not before this run started.
    """
    rows = conn.execute(
        """
        SELECT view_count FROM video_observations
        WHERE creator_handle = ? AND observed_at < ?
        ORDER BY observed_at DESC LIMIT 20
        """,
        (creator_handle, before_timestamp),
    ).fetchall()
    return [r[0] for r in rows if r[0] is not None]

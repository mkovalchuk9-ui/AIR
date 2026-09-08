"""
Lightweight SQLite storage so we can build up a per-artist view-count
history over time (needed to detect "higher than normal" spikes).
The db file itself is committed back to the repo by the GitHub Actions
workflow after each run, so history persists across daily runs.
"""

import sqlite3
import os
import time
from typing import Any

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
    observed_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_creator ON video_observations (creator_handle);
"""


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def record_observation(conn: sqlite3.Connection, video: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO video_observations
            (creator_handle, video_url, view_count, caption_text, bio_text,
             genre_tag, market, observed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            video.get("creator_handle"),
            video.get("video_url"),
            video.get("view_count"),
            video.get("caption_text"),
            video.get("bio_text"),
            video.get("_genre_tag"),
            video.get("_market"),
            int(time.time()),
        ),
    )


def get_artist_history(
    conn: sqlite3.Connection, creator_handle: str, exclude_video_url: str | None = None
) -> list[int]:
    """Return this artist's prior recorded view counts, most recent first."""
    query = "SELECT view_count FROM video_observations WHERE creator_handle = ?"
    params: list[Any] = [creator_handle]
    if exclude_video_url:
        query += " AND (video_url IS NULL OR video_url != ?)"
        params.append(exclude_video_url)
    query += " ORDER BY observed_at DESC LIMIT 20"
    rows = conn.execute(query, params).fetchall()
    return [r[0] for r in rows if r[0] is not None]

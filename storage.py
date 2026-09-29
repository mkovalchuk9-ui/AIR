"""
Lightweight SQLite storage so we can build up a per-artist view-count
history over time (needed to detect "higher than normal" spikes).
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
    follower_count INTEGER,
    observed_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_creator ON video_observations (creator_handle);
"""


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.executescript(SCHEMA)

    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(video_observations)")}
    if "posted_at" not in existing_cols:
        conn.execute("ALTER TABLE video_observations ADD COLUMN posted_at INTEGER")
    if "follower_count" not in existing_cols:
        conn.execute("ALTER TABLE video_observations ADD COLUMN follower_count INTEGER")
    conn.commit()

    return conn


def parse_post_date(post_date_value) -> Optional[int]:
    if post_date_value is None:
        return None
    if isinstance(post_date_value, (int, float)):
        value = int(post_date_value)
        return value // 1000 if value > 100_000_000_000 else value
    if isinstance(post_date_value, str):
        text = post_date_value.strip()
        if not text:
            return None
        if text.isdigit():
            value = int(text)
            return value // 1000 if value > 100_000_000_000 else value
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            return None
    return None


def record_observation(conn: sqlite3.Connection, video: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO video_observations
            (creator_handle, video_url, view_count, caption_text, bio_text,
             genre_tag, market, posted_at, follower_count, observed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            video.get("follower_count"),
            int(time.time()),
        ),
    )


def get_artist_history(
    conn: sqlite3.Connection, creator_handle: str, before_timestamp: int
) -> list[int]:
    rows = conn.execute(
        """
        SELECT view_count FROM video_observations
        WHERE creator_handle = ? AND observed_at < ?
        ORDER BY observed_at DESC LIMIT 20
        """,
        (creator_handle, before_timestamp),
    ).fetchall()
    return [r[0] for r in rows if r[0] is not None]

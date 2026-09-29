"""
Turns raw scraped video records into a filtered, flagged shortlist.
"""

import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Optional

import config
import storage

logger = logging.getLogger("tiktok_scout.analyzer")

_COVER_YEAR_BY_RE = re.compile(config.COVER_YEAR_BY_PATTERN, re.IGNORECASE)


@dataclass
class Flagged:
    creator_handle: str
    creator_display_name: Optional[str]
    video_url: Optional[str]
    caption_text: Optional[str]
    view_count: int
    baseline_avg: float
    multiple: float
    genre_tag: Optional[str]
    market: Optional[str]
    unsigned_confidence: str
    posted_days_ago: Optional[int]
    follower_count: Optional[int]


def _normalize_view_count(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str):
        cleaned = raw.strip().lower().replace(",", "")
        try:
            if cleaned.endswith("k"):
                return int(float(cleaned[:-1]) * 1_000)
            if cleaned.endswith("m"):
                return int(float(cleaned[:-1]) * 1_000_000)
            if cleaned.endswith("b"):
                return int(float(cleaned[:-1]) * 1_000_000_000)
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def looks_signed(bio_text: Optional[str], caption_text: Optional[str]) -> bool:
    text = f"{bio_text or ''} {caption_text or ''}".lower()
    return any(keyword in text for keyword in config.LABEL_EXCLUDE_KEYWORDS)


def looks_like_cover(caption_text: Optional[str]) -> bool:
    text = (caption_text or "").lower()
    if any(phrase in text for phrase in config.COVER_INDICATOR_PHRASES):
        return True
    if _COVER_YEAR_BY_RE.search(caption_text or ""):
        return True
    return False


def looks_like_promo_account(caption_text: Optional[str]) -> bool:
    text = (caption_text or "").lower()
    return any(phrase in text for phrase in config.PROMO_INDICATOR_PHRASES)


def confidence_note(bio_text: Optional[str]) -> str:
    text = (bio_text or "").lower()
    if any(sig in text for sig in config.UNSIGNED_POSITIVE_SIGNALS):
        return "likely_unsigned (bio confirms)"
    return "unclear (no explicit bio signal — spot check)"


def process(raw_videos: list[dict[str, Any]], conn: sqlite3.Connection) -> list[Flagged]:
    flagged: list[Flagged] = []
    seen_handles_this_run: set[str] = set()
    run_started_at = int(time.time())

    for video in raw_videos:
        handle = video.get("creator_handle")
        if not handle:
            continue

        view_count = _normalize_view_count(video.get("view_count"))
        if view_count is None or view_count < config.MIN_ABSOLUTE_VIEWS:
            continue

        follower_count = video.get("follower_count")
        if follower_count is not None and follower_count > config.MAX_FOLLOWER_COUNT:
            logger.info("Excluding %s: %d followers exceeds ceiling", handle, follower_count)
            continue

        caption = video.get("caption_text")

        if looks_signed(video.get("bio_text"), caption):
            logger.info("Excluding %s: label keyword match", handle)
            continue

        if looks_like_cover(caption):
            logger.info("Excluding %s: looks like a cover/nostalgia post", handle)
            continue

        if looks_like_promo_account(caption):
            logger.info("Excluding %s: looks like a promo/aggregator account", handle)
            continue

        history = storage.get_artist_history(conn, handle, before_timestamp=run_started_at)

        posted_at = storage.parse_post_date(video.get("post_date_text"))
        posted_days_ago = None
        if posted_at is not None:
            posted_days_ago = max(0, (run_started_at - posted_at) // 86400)

        storage.record_observation(conn, video)

        if len(history) < config.MIN_HISTORY_POINTS:
            continue

        if posted_days_ago is None:
            logger.info("Skipping %s: no parseable post date, can't confirm recency", handle)
            continue
        if posted_days_ago > config.MAX_VIDEO_AGE_DAYS:
            logger.info(
                "Skipping %s: video is %d days old (max is %d)",
                handle, posted_days_ago, config.MAX_VIDEO_AGE_DAYS,
            )
            continue

        baseline_avg = sum(history) / len(history)
        if baseline_avg <= 0:
            continue

        multiple = view_count / baseline_avg
        if multiple >= config.SPIKE_MULTIPLIER:
            dedup_key = f"{handle}:{video.get('video_url')}"
            if dedup_key in seen_handles_this_run:
                continue
            seen_handles_this_run.add(dedup_key)

            flagged.append(
                Flagged(
                    creator_handle=handle,
                    creator_display_name=video.get("creator_display_name"),
                    video_url=video.get("video_url"),
                    caption_text=caption,
                    view_count=view_count,
                    baseline_avg=round(baseline_avg, 1),
                    multiple=round(multiple, 2),
                    genre_tag=video.get("_genre_tag"),
                    market=video.get("_market"),
                    unsigned_confidence=confidence_note(video.get("bio_text")),
                    posted_days_ago=posted_days_ago,
                    follower_count=follower_count,
                )
            )

    conn.commit()
    flagged.sort(key=lambda f: f.multiple, reverse=True)
    logger.info("Flagged %d videos as spikes", len(flagged))
    return flagged

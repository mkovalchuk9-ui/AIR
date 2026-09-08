"""
Turns raw scraped video records into a filtered, flagged shortlist:
  1. Normalizes/validates each record
  2. Applies the unsigned-vs-signed heuristic (bio keyword check)
  3. Computes each artist's rolling view-count baseline from history
  4. Flags videos that spike well above that baseline
"""

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

import config
import storage

logger = logging.getLogger("tiktok_scout.analyzer")


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
    unsigned_confidence: str  # "likely_unsigned" | "unclear" | note if excluded upstream


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
    """
    Heuristic only. Returns True if we find a known-label mention in the
    artist's bio or caption text. This will miss labels not on the list and
    can occasionally false-positive (e.g. a cover song caption mentioning a
    label). Treat the resulting shortlist as a starting point for manual
    review, not a verified "unsigned" guarantee.
    """
    text = f"{bio_text or ''} {caption_text or ''}".lower()
    return any(keyword in text for keyword in config.LABEL_EXCLUDE_KEYWORDS)


def confidence_note(bio_text: Optional[str]) -> str:
    text = (bio_text or "").lower()
    if any(sig in text for sig in config.UNSIGNED_POSITIVE_SIGNALS):
        return "likely_unsigned (bio confirms)"
    return "unclear (no explicit bio signal — spot check)"


def process(raw_videos: list[dict[str, Any]], conn: sqlite3.Connection) -> list[Flagged]:
    flagged: list[Flagged] = []
    seen_handles_this_run: set[str] = set()

    for video in raw_videos:
        handle = video.get("creator_handle")
        if not handle:
            continue

        view_count = _normalize_view_count(video.get("view_count"))
        if view_count is None or view_count < config.MIN_ABSOLUTE_VIEWS:
            continue

        if looks_signed(video.get("bio_text"), video.get("caption_text")):
            logger.info("Excluding %s: label keyword match", handle)
            continue

        history = storage.get_artist_history(conn, handle, exclude_video_url=video.get("video_url"))

        # Always record the observation so history builds up over time,
        # even if we don't have enough data yet to flag it today.
        storage.record_observation(conn, video)

        if len(history) < config.MIN_HISTORY_POINTS:
            continue  # not enough history yet to judge "higher than normal"

        baseline_avg = sum(history) / len(history)
        if baseline_avg <= 0:
            continue

        multiple = view_count / baseline_avg
        if multiple >= config.SPIKE_MULTIPLIER:
            # Avoid duplicate entries for the same artist within one run
            dedup_key = f"{handle}:{video.get('video_url')}"
            if dedup_key in seen_handles_this_run:
                continue
            seen_handles_this_run.add(dedup_key)

            flagged.append(
                Flagged(
                    creator_handle=handle,
                    creator_display_name=video.get("creator_display_name"),
                    video_url=video.get("video_url"),
                    caption_text=video.get("caption_text"),
                    view_count=view_count,
                    baseline_avg=round(baseline_avg, 1),
                    multiple=round(multiple, 2),
                    genre_tag=video.get("_genre_tag"),
                    market=video.get("_market"),
                    unsigned_confidence=confidence_note(video.get("bio_text")),
                )
            )

    conn.commit()
    flagged.sort(key=lambda f: f.multiple, reverse=True)
    logger.info("Flagged %d videos as spikes", len(flagged))
    return flagged

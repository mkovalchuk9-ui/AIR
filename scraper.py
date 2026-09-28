"""
TikTok data collection via paul_44/tiktok-search, a keyword-search Actor.
Replaces the earlier two-stage hashtag-discovery + profile-recheck system.

This actor searches TikTok's own search index by keyword and supports a
native dateRange filter, so recency is enforced at the source in one call
per genre.

TRADEOFF: this actor doesn't return an artist's bio text, so the
label-exclusion check can only scan video captions now, not bios.

This is a smaller, community-built Actor, so check logs for failures
the way you would for any new dependency.
"""

import os
import time
import logging
from typing import Any

from apify_client import ApifyClient

import config

logger = logging.getLogger("tiktok_scout.scraper")

ACTOR_ID = "paul_44/tiktok-search"


def get_client() -> ApifyClient:
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError("APIFY_API_TOKEN is not set.")
    return ApifyClient(token)


def _get_dataset_id(run) -> str | None:
    """Apify's client may return a dict or an object depending on version."""
    if isinstance(run, dict):
        return run.get("defaultDatasetId")
    for attr in ("default_dataset_id", "defaultDatasetId"):
        if hasattr(run, attr):
            return getattr(run, attr)
    return None


def _normalize(text: str) -> str:
    """Lowercase and strip spaces/hyphens/underscores/# so that
    'singer-songwriter', 'singer songwriter' and '#singersongwriter'
    all compare equal."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _hashtag_text(item: dict) -> str:
    """Flatten the item's hashtags (list of strings or dicts) into one string."""
    tags = item.get("hashtags") or []
    parts = []
    for tag in tags:
        if isinstance(tag, str):
            parts.append(tag)
        elif isinstance(tag, dict):
            parts.append(str(tag.get("name") or tag.get("title") or ""))
    return " ".join(parts)


def matches_genre_term(caption_text: str | None, hashtag_text: str, genre_term: str) -> bool:
    """True if the genre word appears in the caption or hashtags,
    ignoring case, spaces and hyphens."""
    haystack = _normalize(f"{caption_text or ''} {hashtag_text}")
    return _normalize(genre_term) in haystack


def search_genre(genre_label: str, query: str) -> list[dict[str, Any]]:
    """Run one keyword search for a single genre's query."""
    client = get_client()
    logger.info('Searching "%s" (genre=%s)', query, genre_label)

    run_input = {
        "keywords": [query],
        "maxItems": config.SEARCH_MAX_ITEMS,
        "dateRange": config.SEARCH_DATE_RANGE,
        "sortType": config.SEARCH_SORT_TYPE,
        "location": config.SEARCH_LOCATION,
        "strictKeywordMatch": False,
    }

    try:
        run = client.actor(ACTOR_ID).call(run_input=run_input)
    except Exception as exc:  # noqa: BLE001
        logger.warning('Search failed for "%s": %s', query, exc)
        return []

    dataset_id = _get_dataset_id(run)
    if not dataset_id:
        logger.warning('No dataset id in search result for "%s"', query)
        return []

    videos = []
    raw_count = 0
    dropped_relevance = 0
    dropped_genre = 0
    sample_dropped: list[str] = []

    try:
        for item in client.dataset(dataset_id).iterate_items():
            raw_count += 1
            channel = item.get("channel") or {}
            caption = item.get("title")

            if item.get("keywordRelevance") == "none":
                dropped_relevance += 1
                if len(sample_dropped) < 3:
                    sample_dropped.append(f"[relevance=none] {(caption or '')[:80]}")
                continue
            if not matches_genre_term(caption, _hashtag_text(item), genre_label):
                dropped_genre += 1
                if len(sample_dropped) < 3:
                    sample_dropped.append(f"[no genre word] {(caption or '')[:80]}")
                continue

            videos.append({
                "creator_handle": channel.get("username"),
                "creator_display_name": channel.get("name"),
                "video_url": item.get("url"),
                "caption_text": caption,
                "view_count": item.get("views"),
                "post_date_text": item.get("uploadedAt"),
                "bio_text": None,
                "_source_url": item.get("url"),
                "_signal_tag": None,
                "_market": config.SEARCH_LOCATION,
                "_genre_tag": genre_label,
            })
    except Exception as exc:  # noqa: BLE001
        logger.warning('Failed reading dataset for "%s": %s', query, exc)
        return []

    logger.info(
        'DIAG "%s": actor returned %d | dropped for relevance=none: %d | '
        'dropped for missing genre word: %d | kept: %d',
        query, raw_count, dropped_relevance, dropped_genre, len(videos),
    )
    for sample in sample_dropped:
        logger.info("DIAG   sample dropped -> %s", sample)

    time.sleep(config.REQUEST_PAUSE_SECONDS)
    return videos


def collect_all() -> list[dict[str, Any]]:
    """One direct search per configured genre query."""
    all_videos: list[dict[str, Any]] = []

    for genre_label, query in config.DISCOVERY_QUERIES:
        all_videos.extend(search_genre(genre_label, query))

    logger.info("Collected %d video(s) across all genre searches", len(all_videos))
    return all_videos

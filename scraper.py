"""
TikTok data collection via paul_44/tiktok-search, a keyword-search Actor.
Replaces the earlier two-stage hashtag-discovery + profile-recheck system.

TUNING HISTORY:
- v1 hard-filtered out anything the actor tagged keywordRelevance="none",
  assuming that meant "unrelated." Real-world testing showed this dropping
  genuinely on-target results (e.g. a band's own post that literally said
  "small unsigned band" got thrown out this way) — so that filter was
  actively hurting recall for reasons not fully understood, and was removed.
- v2 (this version) trusts the search query itself as the targeting
  mechanism (each query already names the genre, e.g. "unsigned rock
  artist") rather than layering a second hard requirement that the genre
  word appear verbatim in the caption too.
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

    try:
        for item in client.dataset(dataset_id).iterate_items():
            raw_count += 1
            channel = item.get("channel") or {}
            caption = item.get("title")

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

    logger.info('DIAG "%s": actor returned %d | kept: %d', query, raw_count, len(videos))
    time.sleep(config.REQUEST_PAUSE_SECONDS)
    return videos


def collect_all() -> list[dict[str, Any]]:
    """One direct search per configured genre query."""
    all_videos: list[dict[str, Any]] = []

    for genre_label, query in config.DISCOVERY_QUERIES:
        all_videos.extend(search_genre(genre_label, query))

    logger.info("Collected %d video(s) across all genre searches", len(all_videos))
    return all_videos

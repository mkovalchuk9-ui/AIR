"""
TikTok data collection via paul_44/tiktok-search, a keyword-search Actor.
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
    if isinstance(run, dict):
        return run.get("defaultDatasetId")
    for attr in ("default_dataset_id", "defaultDatasetId"):
        if hasattr(run, attr):
            return getattr(run, attr)
    return None


def search_genre(genre_label: str, query: str) -> list[dict[str, Any]]:
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
                "follower_count": channel.get("followers"),
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


def _dedup_by_video_url(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for video in videos:
        url = video.get("video_url")
        key = url or f"{video.get('creator_handle')}::{video.get('caption_text')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(video)
    return deduped


def collect_all() -> list[dict[str, Any]]:
    all_videos: list[dict[str, Any]] = []

    for genre_label, query in config.DISCOVERY_QUERIES:
        all_videos.extend(search_genre(genre_label, query))

    before_dedup = len(all_videos)
    all_videos = _dedup_by_video_url(all_videos)
    if before_dedup != len(all_videos):
        logger.info("Deduped %d duplicate video(s) within this run", before_dedup - len(all_videos))

    logger.info("Collected %d video(s) across all genre searches", len(all_videos))
    return all_videos

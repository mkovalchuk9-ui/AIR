"""
Two-stage TikTok data collection via Apify's TikTok Scraper (Clockworks).

WHY TWO STAGES:
Hashtag-mode results are ranked by popularity, not chronology — TikTok gives
no way to ask a hashtag page for "just the newest posts." Testing showed
this surfacing videos anywhere from 7 days old to over 6 years old under
the same "unsigned" tags. A recency filter alone can't fix that if the
underlying data was never recent to begin with.

So: Stage 1 uses hashtag scraping only to DISCOVER candidate artist handles
(what it's actually good at). Stage 2 re-queries each discovered artist's
own profile with profileSorting="latest" — which genuinely does return
their most recent uploads in order — and only those videos are evaluated
for spikes. This costs roughly double the Apify calls (one extra per
discovered artist) but actually delivers "recently posted video," which
hashtag-only discovery could not.
"""

import os
import time
import logging
from typing import Any

from apify_client import ApifyClient

import config

logger = logging.getLogger("tiktok_scout.scraper")

ACTOR_ID = "clockworks/tiktok-scraper"


def get_client() -> ApifyClient:
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError(
            "APIFY_API_TOKEN is not set. Get one at apify.com "
            "(Settings > Integrations in Apify Console) and add it as a "
            "GitHub Actions secret named APIFY_API_TOKEN."
        )
    return ApifyClient(token)


def _get_dataset_id(run) -> str | None:
    """
    Apify's client can return the run result as either a dict or an object
    with attributes depending on library version — handle both rather than
    assuming one shape.
    """
    if isinstance(run, dict):
        return run.get("defaultDatasetId")
    for attr in ("default_dataset_id", "defaultDatasetId"):
        if hasattr(run, attr):
            return getattr(run, attr)
    return None


def matches_a_genre(caption_text, bio_text):
    """
    Check text against configured genre keywords. Returns the first
    matching genre label, or None if nothing matches.
    """
    text = f"{caption_text or ''} {bio_text or ''}".lower()
    for genre in config.GENRE_HASHTAGS:
        if genre.lower() in text:
            return genre
    return None


def _video_from_item(item: dict, extra: dict) -> dict:
    author = item.get("authorMeta") or {}
    video = {
        "creator_handle": author.get("name"),
        "creator_display_name": author.get("nickName"),
        "video_url": item.get("webVideoUrl"),
        "caption_text": item.get("text"),
        "view_count": item.get("playCount"),
        "post_date_text": item.get("createTimeISO"),
        "bio_text": author.get("signature"),
        "_source_url": item.get("webVideoUrl"),
    }
    video.update(extra)
    return video


# ---------------------------------------------------------------------------
# STAGE 1 — discover candidate artists via hashtags
# ---------------------------------------------------------------------------

def discover_hashtag(tag: str, market: str) -> list[dict[str, Any]]:
    """Run the actor in hashtag mode — used only for discovery, not scoring."""
    client = get_client()
    logger.info("Discovering via hashtag #%s (market=%s)", tag, market)

    run_input = {
        "hashtags": [tag],
        "resultsPerPage": config.VIDEOS_PER_HASHTAG,
        "proxyCountryCode": "None",
        "shouldDownloadCovers": False,
        "shouldDownloadVideos": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadSlideshowImages": False,
    }

    try:
        run = client.actor(ACTOR_ID).call(run_input=run_input)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Apify hashtag run failed for #%s: %s", tag, exc)
        return []

    dataset_id = _get_dataset_id(run)
    if not dataset_id:
        logger.warning("No dataset id in hashtag run result for #%s", tag)
        return []

    videos = []
    try:
        for item in client.dataset(dataset_id).iterate_items():
            videos.append(_video_from_item(item, {"_signal_tag": tag, "_market": market}))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed reading dataset for #%s: %s", tag, exc)
        return []

    logger.info("Discovered %d video(s) under #%s", len(videos), tag)
    time.sleep(config.REQUEST_PAUSE_SECONDS)
    return videos


# ---------------------------------------------------------------------------
# STAGE 2 — pull each discovered artist's own latest videos (genuine recency)
# ---------------------------------------------------------------------------

def fetch_latest_for_profile(handle: str, genre_tag: str, market: str) -> list[dict[str, Any]]:
    """
    Ask the actor for this profile's own videos sorted by latest. Unlike
    hashtag mode, profile mode genuinely supports chronological sorting.
    """
    client = get_client()
    logger.info("Checking latest videos for @%s (genre=%s)", handle, genre_tag)

    run_input = {
        "profiles": [handle],
        "profileSorting": "latest",
        "resultsPerPage": config.PROFILE_VIDEOS_PER_ARTIST,
        "proxyCountryCode": "None",
        "shouldDownloadCovers": False,
        "shouldDownloadVideos": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadSlideshowImages": False,
    }

    try:
        run = client.actor(ACTOR_ID).call(run_input=run_input)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Apify profile run failed for @%s: %s", handle, exc)
        return []

    dataset_id = _get_dataset_id(run)
    if not dataset_id:
        logger.warning("No dataset id in profile run result for @%s", handle)
        return []

    videos = []
    try:
        for item in client.dataset(dataset_id).iterate_items():
            videos.append(_video_from_item(
                item, {"_signal_tag": None, "_market": market, "_genre_tag": genre_tag}
            ))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed reading profile dataset for @%s: %s", handle, exc)
        return []

    logger.info("Got %d latest video(s) for @%s", len(videos), handle)
    time.sleep(config.REQUEST_PAUSE_SECONDS)
    return videos


def collect_all() -> list[dict[str, Any]]:
    """
    Stage 1: sweep hashtags to discover candidate artists matching your
    genres. Stage 2: re-check each discovered artist's own profile for
    their genuinely latest videos, which is what actually gets returned
    for scoring.
    """
    discovery_videos: list[dict[str, Any]] = []
    for market, market_cfg in config.MARKETS.items():
        tags = list(config.SIGNAL_HASHTAGS) + list(market_cfg["extra_tags"])
        for tag in tags:
            discovery_videos.extend(discover_hashtag(tag, market))

    logger.info("Stage 1 discovery: %d raw video records", len(discovery_videos))

    # Genre attribution belongs to the ARTIST, decided once from whatever
    # discovery video first matched — all of that artist's profile videos
    # inherit it, rather than re-checking genre keywords against videos
    # that may not individually mention the genre in their caption.
    handle_to_genre: dict[str, str] = {}
    handle_to_market: dict[str, str] = {}
    for video in discovery_videos:
        handle = video.get("creator_handle")
        if not handle or handle in handle_to_genre:
            continue
        genre = matches_a_genre(video.get("caption_text"), video.get("bio_text"))
        if genre:
            handle_to_genre[handle] = genre
            handle_to_market[handle] = video.get("_market")

    logger.info("Stage 1 result: %d unique genre-matched artists to check", len(handle_to_genre))

    final_videos: list[dict[str, Any]] = []
    for handle, genre in handle_to_genre.items():
        market = handle_to_market.get(handle, "US")
        final_videos.extend(fetch_latest_for_profile(handle, genre, market))

    logger.info("Stage 2 result: %d videos from genuinely-latest profile checks", len(final_videos))
    return final_videos

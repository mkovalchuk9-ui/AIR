"""
Handles all Firecrawl calls.

REVISION NOTE: the original version of this file tried to find genre+signal
matches via Firecrawl's /search (a general web search index) using queries
like `site:tiktok.com "#folk" (#unsigned OR ...)`. That returned zero results
in practice — TikTok hashtag/video content is JS-rendered and poorly indexed
by general search engines, so there was rarely a matching page to even scrape.

This version scrapes real TikTok hashtag pages directly (the actual URLs,
not a search for them), pulling from the unsigned-signal tags, and does
genre matching afterward in Python by checking each video's caption/bio
text against your genre keywords. This is more reliable because it always
points at a real page, rather than hoping a search engine indexed one that
matches a multi-hashtag query.

IMPORTANT REALITY CHECK ON TIKTOK SCRAPING (still applies):
TikTok is aggressively bot-protected. Firecrawl's headless-browser stack
handles a lot of JS-rendered sites well, but TikTok pages can still return
partial data, get rate limited, or get blocked outright. This script fails
gracefully (skip and log) rather than crash. If "Collected 0 raw video
records" persists after this change, the next thing to check is whether
Firecrawl's own dashboard/logs show these specific scrape requests
succeeding or erroring — that tells us if it's a Firecrawl-side block vs.
something in our extraction logic.
"""

import os
import time
import logging
from typing import Any

from firecrawl import Firecrawl

import config

logger = logging.getLogger("tiktok_scout.scraper")


def get_client() -> Firecrawl:
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        raise RuntimeError(
            "FIRECRAWL_API_KEY is not set. This is your firecrawl.dev API key "
            "(from your Firecrawl dashboard) — a separate thing from any Claude.ai "
            "connector, since this script runs independently of Claude chat."
        )
    return Firecrawl(api_key=api_key)


VIDEO_EXTRACT_PROMPT = """
Extract every distinct TikTok video visible on this page. If this page did
not load real TikTok content (e.g. it shows a login wall, captcha, or empty
shell), return an empty videos list rather than guessing.
"""

# Explicit schema, rather than relying on the model to freely decide the
# output shape from a text prompt alone. view_count stays a string since
# TikTok displays it as "1.2M" / "45K" etc — analyzer.py's parser handles
# converting that to an integer downstream.
VIDEO_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "videos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "creator_handle": {"type": "string"},
                    "creator_display_name": {"type": "string"},
                    "video_url": {"type": "string"},
                    "caption_text": {"type": "string"},
                    "view_count": {"type": "string"},
                    "post_date_text": {"type": "string"},
                    "bio_text": {"type": "string"},
                },
            },
        }
    },
    "required": ["videos"],
}


def matches_a_genre(caption_text, bio_text):
    """
    Check a video's text against configured genre keywords. Returns the
    first matching genre label, or None if nothing matches (in which case
    the caller should discard the video — it's outside your target genres).
    """
    text = f"{caption_text or ''} {bio_text or ''}".lower()
    for genre in config.GENRE_HASHTAGS:
        if genre.lower() in text:
            return genre
    return None


def scrape_hashtag_page(tag: str, market: str) -> list[dict[str, Any]]:
    """Scrape a real TikTok hashtag page directly."""
    client = get_client()
    url = f"https://www.tiktok.com/tag/{tag}"
    logger.info("Scraping hashtag page: %s (market=%s)", url, market)

    try:
        result = client.scrape(
            url,
            formats=[
                {"type": "json", "prompt": VIDEO_EXTRACT_PROMPT, "schema": VIDEO_EXTRACT_SCHEMA}
            ],
            wait_for=6000,
        )
    except Exception as exc:  # noqa: BLE001 - log and continue, don't kill the whole run
        logger.warning("Scrape failed for %s: %s", url, exc)
        return []

    extracted = getattr(result, "json", None) or {}
    if not isinstance(extracted, dict):
        logger.warning("Unexpected extraction shape for %s: %r", url, type(extracted))
        return []

    items = extracted.get("videos")
    if not isinstance(items, list):
        logger.info("No videos extracted from %s (page may not have loaded real content)", url)
        return []

    videos = []
    for item in items:
        item["_source_url"] = url
        item["_signal_tag"] = tag
        item["_market"] = market
        videos.append(item)

    logger.info("Extracted %d video(s) from %s", len(videos), url)
    time.sleep(config.REQUEST_PAUSE_SECONDS)
    return videos


def collect_all() -> list[dict[str, Any]]:
    """
    Sweep every configured signal hashtag (plus market-specific tags),
    then filter down to videos matching your target genres.
    """
    all_videos: list[dict[str, Any]] = []

    for market, market_cfg in config.MARKETS.items():
        tags_to_scrape = list(config.SIGNAL_HASHTAGS) + list(market_cfg["extra_tags"])
        for tag in tags_to_scrape:
            all_videos.extend(scrape_hashtag_page(tag, market))

    logger.info("Collected %d raw video records (before genre filtering)", len(all_videos))

    genre_matched = []
    for video in all_videos:
        genre = matches_a_genre(video.get("caption_text"), video.get("bio_text"))
        if genre:
            video["_genre_tag"] = genre
            genre_matched.append(video)

    logger.info(
        "Collected %d raw video records, %d matched a target genre",
        len(all_videos), len(genre_matched),
    )
    return genre_matched

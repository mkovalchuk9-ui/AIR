"""
Handles all Firecrawl calls.

IMPORTANT REALITY CHECK ON TIKTOK SCRAPING:
TikTok is one of the more aggressively bot-protected platforms on the web.
Firecrawl's headless-browser stack handles a lot of JS-rendered sites well,
but TikTok hashtag/search pages can still return partial data, get rate
limited, or occasionally get blocked outright. This script is built to fail
gracefully (skip and log) rather than crash, but expect to tune waitFor
times and review raw output when you first run this, rather than trusting
the flagged list blindly on day one.
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


# JSON extraction schema Firecrawl's LLM-extraction mode will try to fill in
# from whatever renders on the page. Fields may come back null if the page
# didn't fully load — that's expected and handled downstream.
VIDEO_EXTRACT_PROMPT = """
Extract every distinct TikTok video visible on this page. For each video, return:
- creator_handle (the @username)
- creator_display_name
- video_url
- caption_text
- view_count (as a plain integer, no commas/suffixes — convert "1.2M" to 1200000, "45K" to 45000)
- post_date_text (whatever date/relative-date string is shown, e.g. "3d ago")
- bio_text (the creator's profile bio, if visible on this page)
Return an empty list if no videos are visible or the page failed to load real content.
"""


def search_genre_with_signals(genre_tag: str, market: str) -> list[dict[str, Any]]:
    """
    Query Firecrawl's /search for TikTok content matching a genre tag
    combined (via OR) with the full set of unsigned-signal words, in a
    single query per genre. This keeps call volume to len(genres) x
    len(markets) instead of a full genre x signal cross-product, which
    would burn through rate limits/credits fast for no real benefit.
    """
    client = get_client()
    signal_clause = " OR ".join(f'#{tag}' for tag in config.SIGNAL_HASHTAGS)
    query = f'site:tiktok.com "#{genre_tag}" ({signal_clause})'
    logger.info("Searching: %s (market=%s)", query, market)

    try:
        results = client.search(
            query=query,
            limit=config.RESULTS_PER_QUERY,
            scrape_options={
                "formats": [
                    {"type": "json", "prompt": VIDEO_EXTRACT_PROMPT}
                ],
                "waitFor": 4000,
            },
        )
    except Exception as exc:  # noqa: BLE001 - log and continue, don't kill the whole run
        logger.warning("Search failed for %r: %s", query, exc)
        return []

    videos: list[dict[str, Any]] = []
    for doc in getattr(results, "data", []) or []:
        extracted = getattr(doc, "json", None) or {}
        items = extracted.get("videos") if isinstance(extracted, dict) else None
        if isinstance(items, list):
            for item in items:
                item["_source_url"] = getattr(doc, "url", None)
                item["_genre_tag"] = genre_tag
                item["_signal_tag"] = None  # combined query, no single signal tag to attribute
                item["_market"] = market
                videos.append(item)

    time.sleep(config.REQUEST_PAUSE_SECONDS)
    return videos


def scrape_hashtag_page(tag: str, market: str) -> list[dict[str, Any]]:
    """
    Directly scrape a TikTok hashtag page as a secondary source.
    More likely to get partial/blocked results than the search-based approach
    above, but worth trying since it can surface videos search misses.
    """
    client = get_client()
    url = f"https://www.tiktok.com/tag/{tag}"
    logger.info("Scraping hashtag page: %s (market=%s)", url, market)

    try:
        result = client.scrape(
            url,
            formats=[{"type": "json", "prompt": VIDEO_EXTRACT_PROMPT}],
            wait_for=6000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scrape failed for %s: %s", url, exc)
        return []

    extracted = getattr(result, "json", None) or {}
    items = extracted.get("videos") if isinstance(extracted, dict) else None
    videos = []
    if isinstance(items, list):
        for item in items:
            item["_source_url"] = url
            item["_genre_tag"] = None
            item["_signal_tag"] = tag
            item["_market"] = market
            videos.append(item)

    time.sleep(config.REQUEST_PAUSE_SECONDS)
    return videos


def collect_all() -> list[dict[str, Any]]:
    """Run the full sweep across all configured markets, genres, and signal tags."""
    all_videos: list[dict[str, Any]] = []

    for market, market_cfg in config.MARKETS.items():
        # Genre + combined-signal searches (primary source, higher precision)
        for genre_tag in config.GENRE_HASHTAGS:
            all_videos.extend(search_genre_with_signals(genre_tag, market))

        # Market-specific extra tags, scraped directly
        for tag in market_cfg["extra_tags"]:
            all_videos.extend(scrape_hashtag_page(tag, market))

    logger.info("Collected %d raw video records", len(all_videos))
    return all_videos

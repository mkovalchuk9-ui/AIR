"""
Handles all TikTok data collection via Apify's TikTok Scraper (built by
Clockworks, maintained by Apify — one of the most widely used TikTok
scrapers on the platform, purpose-built to handle TikTok's anti-bot defenses
with rotating proxies etc.).

REVISION HISTORY:
- v1 tried Firecrawl's /search (general web search index) — returned zero
  results because TikTok content isn't well indexed by search engines.
- v2 tried Firecrawl's direct scrape of TikTok hashtag pages — Firecrawl
  explicitly does not support tiktok.com at all ("Website Not Supported"),
  confirmed via their own error message. No amount of tuning fixes that.
- v3 (this version) uses Apify's dedicated TikTok Scraper actor, which is
  built specifically to get past TikTok's bot detection.

Each hashtag is run as its own Apify Actor call so we can cleanly tag which
hashtag produced which result (mirrors the old Firecrawl-based structure).
Genre matching still happens afterward in Python, since TikTok/Apify have
no way to combine "genre AND unsigned-signal" in one query.
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
            "APIFY_API_TOKEN is not set. Get one free at apify.com "
            "(Settings > Integrations in Apify Console) and add it as a "
            "GitHub Actions secret named APIFY_API_TOKEN."
        )
    return ApifyClient(token)


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


def scrape_hashtag(tag: str, market: str) -> list[dict[str, Any]]:
    """Run the Apify TikTok Scraper actor for a single hashtag."""
    client = get_client()
    logger.info("Scraping hashtag #%s via Apify (market=%s)", tag, market)

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
    except Exception as exc:  # noqa: BLE001 - log and continue, don't kill the whole run
        logger.warning("Apify run failed for #%s: %s", tag, exc)
        return []

    videos = []
    try:
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            author = item.get("authorMeta") or {}
            videos.append({
                "creator_handle": author.get("name"),
                "creator_display_name": author.get("nickName"),
                "video_url": item.get("webVideoUrl"),
                "caption_text": item.get("text"),
                "view_count": item.get("playCount"),
                "post_date_text": item.get("createTimeISO"),
                "bio_text": author.get("signature"),
                "_source_url": item.get("webVideoUrl"),
                "_signal_tag": tag,
                "_market": market,
            })
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed reading Apify dataset for #%s: %s", tag, exc)
        return []

    logger.info("Got %d video(s) for #%s", len(videos), tag)
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
            all_videos.extend(scrape_hashtag(tag, market))

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

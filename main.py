"""
Entry point. Run manually with: python main.py
Run daily via .github/workflows/daily-scan.yml
"""

import logging

import scraper
import storage
import analyzer
import webreport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tiktok_scout.main")


def main() -> None:
    logger.info("Starting daily TikTok scout run")

    raw_videos = scraper.collect_all()

    conn = storage.get_connection()
    try:
        flagged = analyzer.process(raw_videos, conn)
    finally:
        conn.close()

    webreport.write(flagged, market_scope="US")
    logger.info("Run complete. %d artists flagged.", len(flagged))


if __name__ == "__main__":
    main()

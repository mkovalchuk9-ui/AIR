"""
Central configuration for the TikTok unsigned-artist scout.
Edit this file to tune markets, genres, hashtags, and thresholds —
you shouldn't need to touch scraper.py / analyzer.py / reporter.py for routine changes.
"""

# ---------------------------------------------------------------------------
# GENRES
# ---------------------------------------------------------------------------
GENRES = [
    "alternative",
    "rock",
    "singer songwriter",
    "folk",
    "americana",
]

# ---------------------------------------------------------------------------
# HASHTAGS
# "signal" tags = used to indicate the artist is unsigned/independent/new.
# "genre" tags  = used to indicate the genre. These are paired together in
# queries (genre + signal) rather than searched alone, since bare genre tags
# return mostly signed/major-label content.
# ---------------------------------------------------------------------------
SIGNAL_HASHTAGS = [
    "unsigned",
    "unsignedartist",
    "unsignedmusician",
    "unsignedtalent",
    "unreleased",
    "newartist",
    "independentartist",
    "diymusician",
    "originalmusic",
    "undiscoveredartist",
    "upcomingartist",
    "musiciansoftiktok",
]

GENRE_HASHTAGS = [
    "alternative",
    "alternativemusic",
    "rock",
    "rockmusic",
    "singersongwriter",
    "singersongwriterlife",
    "folk",
    "folkmusic",
    "indiefolk",
    "indierock",
    "altfolk",
    "americana",
    "americanamusic",
]

# ---------------------------------------------------------------------------
# MARKETS
# TikTok hashtag pages aren't natively geo-split, so "market" is approximated
# via market-specific tag variants + spelling. Add/remove markets here.
# Each market's `extra_tags` are appended to the genre+signal pairing pass.
# ---------------------------------------------------------------------------
MARKETS = {
    "US": {"extra_tags": ["unsignedusa", "americanindieartist"]},
    # Add markets back in later, e.g.:
    # "UK": {"extra_tags": ["unsigneduk", "ukunsigned", "britishindieartist"]},
    # "CA": {"extra_tags": ["unsignedcanada", "canadianindieartist"]},
    # "AU": {"extra_tags": ["unsignedaustralia", "auindieartist", "unsignedaus"]},
}

# ---------------------------------------------------------------------------
# LABEL EXCLUSION LIST (heuristic — not authoritative)
# If any of these strings show up in an artist's bio/linktree text, they're
# flagged as likely SIGNED and excluded from the report. This is a heuristic
# safety net, not proof either way — spot-check borderline cases yourself.
# ---------------------------------------------------------------------------
LABEL_EXCLUDE_KEYWORDS = [
    "universal music", "umg", "sony music", "warner music", "wmg",
    "atlantic records", "columbia records", "republic records", "rca records",
    "capitol records", "interscope", "def jam", "island records",
    "epic records", "elektra", "parlophone", "polydor", "virgin music",
    "big machine", "concord music", "bmg rights", "empire distribution",
    "record label:", "signed to",
]

# Signals that reinforce "unsigned" (used only for logging/confidence, not a hard filter)
UNSIGNED_POSITIVE_SIGNALS = [
    "unsigned", "independent artist", "indie artist", "diy musician",
    "no label", "self released", "self-released",
]

# ---------------------------------------------------------------------------
# OUTLIER DETECTION
# ---------------------------------------------------------------------------
MIN_HISTORY_POINTS = 2          # minimum prior videos on file before we trust a baseline
SPIKE_MULTIPLIER = 2.5          # flag if current views >= this multiple of the artist's rolling average
MIN_ABSOLUTE_VIEWS = 5000       # ignore tiny accounts below this floor, even if "spiking" relatively

# ---------------------------------------------------------------------------
# SCRAPE BEHAVIOR
# ---------------------------------------------------------------------------
RESULTS_PER_QUERY = 5           # how many results Firecrawl returns per search query
REQUEST_PAUSE_SECONDS = 2       # pause between Firecrawl calls to stay well under rate limits

# COST NOTE: JSON-extraction scrapes cost 5 Firecrawl credits each (per the
# Firecrawl pricing model at the time this was written). Rough daily cost =
# (genres x markets x RESULTS_PER_QUERY x 5) + (market extra_tags x 5).
# With defaults (13 genre tags x 4 markets x 5 results): ~1,300 credits/day.
# START SMALL: cut GENRE_HASHTAGS down and/or run one market first to see
# real costs against your Firecrawl plan before scaling up.

# ---------------------------------------------------------------------------
# STORAGE
# ---------------------------------------------------------------------------
DB_PATH = "data/history.db"

# ---------------------------------------------------------------------------
# EMAIL
# Credentials are read from environment variables (set as GitHub Actions
# secrets) — never hardcode them here.
# ---------------------------------------------------------------------------
EMAIL_SUBJECT_PREFIX = "[TikTok Scout] Daily unsigned-artist report"

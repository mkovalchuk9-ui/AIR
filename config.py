"""
Central configuration for the TikTok unsigned-artist scout.
"""

GENRES = [
    "alternative", "rock", "singer songwriter", "folk", "americana",
]

# ---------------------------------------------------------------------------
# LABEL EXCLUSION (heuristic — caption text only; this actor doesn't return bios)
# ---------------------------------------------------------------------------
LABEL_EXCLUDE_KEYWORDS = [
    "universal music", "umg", "sony music", "warner music", "wmg",
    "atlantic records", "columbia records", "republic records", "rca records",
    "capitol records", "interscope", "def jam", "island records",
    "epic records", "elektra", "parlophone", "polydor", "virgin music",
    "big machine", "concord music", "bmg rights", "empire distribution",
    "record label:", "signed to",
]

UNSIGNED_POSITIVE_SIGNALS = [
    "unsigned", "independent artist", "indie artist", "diy musician",
    "no label", "self released", "self-released",
]

# ---------------------------------------------------------------------------
# COVER-SONG / NOSTALGIA-POST EXCLUSION (heuristic, caption text)
# ---------------------------------------------------------------------------
COVER_INDICATOR_PHRASES = [
    "cover of", "(cover)", "cover)", "originally by", "made famous by",
    "originally performed by", "oldiesbutgoodies", "throwback to",
]
COVER_YEAR_BY_PATTERN = r"\bby\b.{0,40}\(\d{4}\)"

# ---------------------------------------------------------------------------
# PROMOTIONAL / AGGREGATOR ACCOUNT EXCLUSION (heuristic, caption text)
# ---------------------------------------------------------------------------
PROMO_INDICATOR_PHRASES = [
    "stream the talented", "check out this artist", "go listen to",
    "discover new music", "new music alert", "go stream", "stream this artist",
    "support this artist", "you need to hear this artist",
]

# ---------------------------------------------------------------------------
# OUTLIER DETECTION
# ---------------------------------------------------------------------------
MIN_HISTORY_POINTS = 1
SPIKE_MULTIPLIER = 1.8
MIN_ABSOLUTE_VIEWS = 5000
MAX_VIDEO_AGE_DAYS = 5
MAX_FOLLOWER_COUNT = 100000

# ---------------------------------------------------------------------------
# SEARCH-BASED DISCOVERY (paul_44/tiktok-search actor)
# ---------------------------------------------------------------------------
DISCOVERY_QUERIES = [
    ("alternative", "alternative artist original song"),
    ("rock", "rock band original music"),
    ("singer songwriter", "singer songwriter original song"),
    ("folk", "folk artist original song"),
    ("americana", "americana artist original song"),
]

SEARCH_MAX_ITEMS = 15
SEARCH_DATE_RANGE = "7days"
SEARCH_SORT_TYPE = "LATEST"
SEARCH_LOCATION = "US"
REQUEST_PAUSE_SECONDS = 2

# ---------------------------------------------------------------------------
# STORAGE
# ---------------------------------------------------------------------------
DB_PATH = "data/history.db"

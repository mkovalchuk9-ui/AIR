# TikTok Unsigned-Artist Scout

Daily scan across TikTok (US market) for artists (alternative, rock,
singer-songwriter, folk, americana) whose recent video is performing well
above their normal view range, with a heuristic filter for likely-unsigned
status. Publishes a small website (via GitHub Pages) you check whenever you
want — no email required.

## Read this before turning it on

**TikTok is hard to scrape reliably.** It has aggressive bot detection and
heavily JS-rendered pages. Firecrawl's headless browser handles a lot of sites
well, but expect some queries to return partial or empty data, especially at
first. Run it manually a few times (`python main.py`) and check the logs /
`data/history.db` before trusting the automated daily email.

**The "unsigned" filter is a heuristic, not a fact-check.** It excludes any
artist whose bio/caption mentions a known label (see `LABEL_EXCLUDE_KEYWORDS`
in `config.py`). It will miss labels not on that list and can't confirm
someone actually *is* unsigned — just that we didn't find a label mention.
Treat the report as a shortlist to verify, not a final answer.

**History takes a few days to build.** The spike detection compares a video's
views against that artist's own rolling average from prior scrapes. Until an
artist has been seen at least `MIN_HISTORY_POINTS` (default: 2) times, they
won't be flagged — this is expected, not a bug.

**Cost.** Each JSON-extraction scrape costs Firecrawl credits (5 credits per
page at time of writing). See the cost note in `config.py` for the formula —
default settings can run ~1,000+ credits/day across 4 markets and 13 genre
tags. Start with fewer genres/markets and a lower `RESULTS_PER_QUERY` to see
real costs against your Firecrawl plan before scaling up.

## Setup

### 1. Get a Firecrawl API key
This is separate from any Claude.ai connector — this script runs on its own,
outside of Claude, so it needs its own key. Go to firecrawl.dev, sign in,
and grab an API key (starts with `fc-`) from your dashboard.

### 2. Push this repo to GitHub
Create a new repo and push everything in this folder to it, including the
`docs/` folder — that's what becomes your website.

### 3. Add the GitHub Actions secret
In your repo: **Settings → Secrets and variables → Actions → New repository secret.**

| Secret name        | Value                          |
|---------------------|--------------------------------|
| `FIRECRAWL_API_KEY` | your `fc-...` key from step 1  |

### 4. Turn on GitHub Pages
**Settings → Pages** → under "Build and deployment", set **Source** to
"Deploy from a branch", branch `main`, folder `/docs`. Save. GitHub will
give you a URL like `https://your-username.github.io/your-repo-name/` —
that's your website. It updates automatically whenever the daily job pushes
new data; there's nothing else to configure.

### 5. Test it manually first
In the repo's **Actions** tab, find "Daily TikTok Scout" and click
**Run workflow** to trigger it manually (this is what `workflow_dispatch`
in the yml enables). Check the run logs, then visit your Pages URL.

Once you've confirmed it works and the cost/data quality look reasonable,
it will run automatically every day at the time set in
`.github/workflows/daily-scan.yml` (default: 13:00 UTC — edit the cron line
to change this).

### 6. (Optional) Run locally instead
```bash
pip install -r requirements.txt
export FIRECRAWL_API_KEY=fc-...
python main.py
```
This writes/updates `docs/data/latest.json` locally — open `docs/index.html`
directly in a browser to preview (or run `python -m http.server` from the
`docs/` folder and visit `localhost:8000`).

### Want email too instead of (or alongside) the website?
`reporter.py` still has the original SMTP-based email code — it's just not
called from `main.py` anymore. Add `import reporter` and
`reporter.send_report(flagged)` back into `main.py`, and add the SMTP
secrets (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`,
`REPORT_TO_EMAIL`) to re-enable it.

## Tuning

Everything you'll want to adjust routinely lives in `config.py`:
- `GENRES` / `GENRE_HASHTAGS` / `SIGNAL_HASHTAGS` — what you're searching for
- `MARKETS` — which regions and their market-specific tags
- `SPIKE_MULTIPLIER` — how far above baseline a video needs to be to get flagged
- `MIN_ABSOLUTE_VIEWS` — floor to ignore tiny/noise accounts
- `LABEL_EXCLUDE_KEYWORDS` — expand this as you spot labels it's missing

## Files

- `main.py` — orchestrates a full run
- `scraper.py` — all Firecrawl calls
- `analyzer.py` — spike detection + unsigned heuristic
- `storage.py` — SQLite history (committed back to the repo each run)
- `webreport.py` — writes `docs/data/latest.json` + `docs/data/runs.json` for the site
- `docs/index.html` — the website itself (fetches the JSON above, no backend)
- `reporter.py` — optional email path, not used by default (see above)
- `config.py` — all the settings above

## Adding markets back later

`config.py` has UK/CA/AU commented out in `MARKETS`. Uncomment what you want,
and change `market_scope="US"` in `main.py`'s call to `webreport.write(...)`
to something like `"US, UK, CA, AU"` once you're running more than one.

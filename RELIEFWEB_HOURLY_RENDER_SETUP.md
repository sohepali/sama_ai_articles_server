# ReliefWeb Hourly Job Setup

ReliefWeb may reject its API if the `appname` is not approved. This job avoids that issue by using ReliefWeb public RSS/listing pages, then fetching each full article page directly with Python.

This is separate from the main FastAPI server:

```text
reliefweb_hourly_job.py
```

It saves into the same Supabase/PostgreSQL article tables used by the standalone articles server.

## Render Cron Job

Create a new **Cron Job** service in Render.

Use the same GitHub repo and the same root directory:

```text
sama_ai_articles_server
```

Build command:

```bash
pip install -r requirements.txt
```

Command:

```bash
python reliefweb_hourly_job.py
```

Schedule, every hour:

```text
0 * * * *
```

Render cron schedules use UTC time.

## Environment variables

Use the same database as the articles server:

```text
DATABASE_URL=your Supabase PostgreSQL connection string
```

Optional settings:

```text
RELIEFWEB_SOURCE_NAME=ReliefWeb
RELIEFWEB_RSS_URL=https://reliefweb.int/updates/rss.xml
RELIEFWEB_LISTING_URL=https://reliefweb.int/updates
RELIEFWEB_MAX_ARTICLES=50
NEWS_MIN_FULL_CHARS=600
NEWS_MAX_DOCUMENTS_PER_ARTICLE=3
NEWS_MAX_DOCUMENT_BYTES=20971520
```

## How the user app works

The user app should not scrape ReliefWeb directly.

The flow should be:

```text
Render Cron Job every hour
  -> reliefweb_hourly_job.py
  -> Supabase PostgreSQL
  -> user clicks Refresh in SAMA AI
  -> GET /articles/sync
```

This means Supabase becomes the central article database, and users only download approved article records from your server.

## Local test

From this folder:

```bash
python reliefweb_hourly_job.py
```

Expected output:

```text
{'source': 'ReliefWeb', 'discovered': ..., 'created': ..., 'updated': ...}
```


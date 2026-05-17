# SAMA AI Articles Server

Standalone FastAPI server for collecting, storing, and syncing articles for SAMA AI.

This server is intentionally separate from the license/admin server. It uses its own PostgreSQL database and its own API tokens.

## What it stores

- Source name and source configuration
- Article title, URL, canonical URL, source, dates
- Raw HTML when fetched by the backend
- Full extracted article text
- Summary text when provided by RSS/n8n
- Extraction status: `success`, `partial`, or `failed`
- Country tags
- Downloaded PDF/Word attachments as PostgreSQL binary data
- Extracted text from PDF/Word attachments
- Ingestion run history

## Render setup

Create a new Render Web Service for this folder.

Use:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn server:app --host 0.0.0.0 --port $PORT
```

Environment variables:

```text
DATABASE_URL=your-postgresql-connection-string
ADMIN_TOKEN=make-a-long-random-admin-token
APP_SYNC_TOKEN=make-a-long-random-app-sync-token
NEWS_MIN_FULL_CHARS=600
NEWS_APPROVE_PARTIAL=false
```

For Supabase, `DATABASE_URL` must be the PostgreSQL connection string, not the project URL.

Correct shape:

```text
postgresql://postgres.PROJECT_REF:PASSWORD@aws-1-REGION.pooler.supabase.com:5432/postgres
```

## Main endpoints

Health:

```http
GET /health
```

Admin dashboard:

```http
GET /admin/dashboard
X-Admin-Token: your-admin-token
```

Seed default RSS sources:

```http
POST /admin/sources/seed
X-Admin-Token: your-admin-token
```

Run ingestion:

```http
POST /admin/ingest/run
X-Admin-Token: your-admin-token
Content-Type: application/json

{}
```

Import articles from n8n JSON:

```http
POST /admin/articles/import-json
X-Admin-Token: your-admin-token
Content-Type: application/json

{
  "articles": [
    {
      "source": "BBC World",
      "title": "Article title",
      "url": "https://example.com/article",
      "published_at": "2026-05-16T12:00:00Z",
      "content": "Full article text here",
      "country_tags": "Syria, Yemen"
    }
  ]
}
```

Compatibility alias for n8n:

```http
POST /admin/news/import-json
```

Windows app sync:

```http
GET /articles/sync
Authorization: Bearer your-app-sync-token
```

Optional query parameters:

```text
since=2026-05-16T00:00:00Z
source=BBC World
country=Syria
limit=500
```

## n8n recommended final node

Use a final Code node in `Run Once for All Items` mode:

```javascript
return [{
  json: {
    articles: items.map(item => ({
      source: item.json.source || "Unknown",
      title: item.json.title || "",
      url: item.json.url || item.json.link || item.json.original_url || "",
      published_at: item.json.published_at || item.json.date || "",
      content: item.json.content || item.json.full_text || item.json.summary || "",
      country_tags: item.json.country_tags || "",
      collected_at: new Date().toISOString()
    }))
  }
}];
```

Then use an HTTP Request node:

- Method: `POST`
- URL: `https://YOUR-RENDER-SERVICE.onrender.com/admin/articles/import-json`
- Header: `X-Admin-Token: your-admin-token`
- Body: JSON
- JSON body: `{{$json}}`

## Local test

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/health
```


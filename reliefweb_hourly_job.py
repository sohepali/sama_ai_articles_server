"""
Standalone ReliefWeb ingestion job for Render Cron Jobs.

This file is intentionally separate from server.py. It reuses the database
models and storage helpers, but it does not add or change API routes.

Run locally:
    python reliefweb_hourly_job.py

Render Cron command:
    python reliefweb_hourly_job.py
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import feedparser
from bs4 import BeautifulSoup

from server import (
    ArticleSource,
    SessionLocal,
    classify_status,
    clean_text,
    extract_text_from_html,
    fetch_html,
    infer_country_tags,
    parse_datetime,
    save_documents_for_article,
    upsert_article_record,
    utc_now,
)


RELIEFWEB_SOURCE_NAME = os.getenv("RELIEFWEB_SOURCE_NAME", "ReliefWeb")
RELIEFWEB_RSS_URL = os.getenv("RELIEFWEB_RSS_URL", "https://reliefweb.int/updates/rss.xml")
RELIEFWEB_LISTING_URL = os.getenv("RELIEFWEB_LISTING_URL", "https://reliefweb.int/updates")
RELIEFWEB_MAX_ARTICLES = int(os.getenv("RELIEFWEB_MAX_ARTICLES", os.getenv("NEWS_MAX_ARTICLES_PER_SOURCE", "50")))


def ensure_reliefweb_source(db) -> ArticleSource:
    source = db.query(ArticleSource).filter(ArticleSource.name == RELIEFWEB_SOURCE_NAME).first()
    if source:
        source.source_type = source.source_type or "reliefweb_public"
        source.rss_url = source.rss_url or RELIEFWEB_RSS_URL
        source.source_page_url = source.source_page_url or RELIEFWEB_LISTING_URL
        source.extractor_type = "reliefweb_public"
        source.active = True
        return source

    source = ArticleSource(
        name=RELIEFWEB_SOURCE_NAME,
        source_type="reliefweb_public",
        rss_url=RELIEFWEB_RSS_URL,
        source_page_url=RELIEFWEB_LISTING_URL,
        extractor_type="reliefweb_public",
        active=True,
        approve_by_default=True,
    )
    db.add(source)
    db.flush()
    return source


def discover_from_reliefweb_rss() -> List[Dict[str, Any]]:
    feed = feedparser.parse(RELIEFWEB_RSS_URL)
    entries = []
    for entry in feed.entries[:RELIEFWEB_MAX_ARTICLES]:
        url = clean_text(entry.get("link") or entry.get("id"))
        title = clean_text(entry.get("title"))
        if not url or not title:
            continue
        entries.append(
            {
                "title": title,
                "url": url,
                "published": entry.get("published") or entry.get("updated") or "",
                "summary": clean_text(entry.get("summary") or entry.get("description")),
                "source": RELIEFWEB_SOURCE_NAME,
                "discovery_method": "rss",
            }
        )
    return entries


def discover_from_reliefweb_listing() -> List[Dict[str, Any]]:
    html = fetch_html(RELIEFWEB_LISTING_URL)
    soup = BeautifulSoup(html, "html.parser")
    entries: List[Dict[str, Any]] = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href.startswith("/"):
            href = "https://reliefweb.int" + href
        if "reliefweb.int/report/" not in href:
            continue
        canonical = href.split("#", 1)[0]
        if canonical in seen:
            continue
        title = clean_text(anchor.get_text(" "))
        if len(title) < 8:
            continue
        seen.add(canonical)
        entries.append(
            {
                "title": title,
                "url": canonical,
                "published": "",
                "summary": "",
                "source": RELIEFWEB_SOURCE_NAME,
                "discovery_method": "listing",
            }
        )
        if len(entries) >= RELIEFWEB_MAX_ARTICLES:
            break
    return entries


def discover_reliefweb_articles() -> List[Dict[str, Any]]:
    entries = discover_from_reliefweb_rss()
    if entries:
        return entries
    return discover_from_reliefweb_listing()


def extract_meta(html: str, *names: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    for name in names:
        tag = (
            soup.find("meta", attrs={"property": name})
            or soup.find("meta", attrs={"name": name})
            or soup.find("meta", attrs={"itemprop": name})
        )
        if tag and tag.get("content"):
            return clean_text(tag["content"])
    return None


def enrich_reliefweb_entry(entry: Dict[str, Any]) -> Tuple[str, str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    url = clean_text(entry.get("url"))
    html = fetch_html(url)
    extracted_text, extractor_used = extract_text_from_html(html, url)

    meta_title = extract_meta(html, "og:title", "twitter:title", "headline")
    meta_date = extract_meta(html, "article:published_time", "datePublished", "pubdate")
    meta_description = extract_meta(html, "og:description", "description")

    title = clean_text(entry.get("title")) or meta_title or url
    published_text = meta_date or clean_text(entry.get("published"))
    published_at, parsed_published_text = parse_datetime(published_text)
    summary = clean_text(entry.get("summary")) or meta_description
    content = extracted_text or summary

    return title, content, summary, published_at, parsed_published_text, html, extractor_used


def ingest_reliefweb_once() -> Dict[str, Any]:
    db = SessionLocal()
    stats = {
        "source": RELIEFWEB_SOURCE_NAME,
        "discovered": 0,
        "created": 0,
        "updated": 0,
        "success": 0,
        "partial": 0,
        "failed": 0,
        "errors": [],
    }

    try:
        source = ensure_reliefweb_source(db)
        entries = discover_reliefweb_articles()
        stats["discovered"] = len(entries)

        for entry in entries:
            url = clean_text(entry.get("url"))
            if not url:
                stats["failed"] += 1
                stats["errors"].append({"title": entry.get("title"), "error": "Missing URL"})
                continue

            try:
                title, content, summary, published_at, published_text, html, extractor_used = enrich_reliefweb_entry(entry)
                status = classify_status(content)
                country_tags = infer_country_tags(f"{title} {content}")
                article, created = upsert_article_record(
                    db=db,
                    source=source,
                    title=title,
                    url=url,
                    content=content,
                    published_at=published_at,
                    published_text=published_text,
                    raw_html=html,
                    summary=summary,
                    status=status,
                    extractor_used=extractor_used or "reliefweb_public",
                    fetch_error=None,
                    country_tags=country_tags,
                    metadata=entry,
                )
                save_documents_for_article(db, article, html, url)
                if created:
                    stats["created"] += 1
                else:
                    stats["updated"] += 1
                if status == "success":
                    stats["success"] += 1
                elif status == "partial":
                    stats["partial"] += 1
                else:
                    stats["failed"] += 1
                db.commit()
            except Exception as exc:
                db.rollback()
                stats["failed"] += 1
                stats["errors"].append({"url": url, "error": str(exc)})

        source.last_run_at = utc_now()
        db.commit()
        return stats
    finally:
        db.close()


if __name__ == "__main__":
    result = ingest_reliefweb_once()
    print(result)


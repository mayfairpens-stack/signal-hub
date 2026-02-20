"""
Maranello Signal pipeline — Ferrari F1 intelligence.

Polls RSS feeds, filters to Ferrari-only content, and synthesizes a
podcast-style narrative via Claude.

Returns {"briefing": "...", "source_links": [...]} (does not build site or deploy).
"""

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import feedparser

log = logging.getLogger(__name__)

FEEDS = [
    {"name": "Formu1a.uno",        "url": "https://www.formu1a.uno/feed/",                                "lang": "it"},
    {"name": "Ferrari Media",      "url": "https://media.ferrari.com/feed/",                              "lang": "en"},
    {"name": "Motorsport.com IT",  "url": "https://it.motorsport.com/rss/f1/news/",                       "lang": "it"},
    {"name": "r/ScuderiaFerrari", "url": "https://www.reddit.com/r/ScuderiaFerrari/new/.rss",             "lang": "en"},
]

SYSTEM_PROMPT = """\
You are the voice of Maranello Signal — a daily podcast-style briefing \
focused exclusively on Scuderia Ferrari.

You receive a batch of raw news items (some in Italian, some in English).

STEP 1 — FILTER: Discard any item that is NOT directly about Ferrari \
(the team, its drivers, its car, its strategy, its management). \
General F1 news that only mentions Ferrari in passing should be dropped.

STEP 2 — SYNTHESIZE: Combine the remaining Ferrari items into a single \
conversational briefing written as if you are the host of a morning \
podcast segment. Be informal, engaging, and knowledgeable — like a \
well-connected paddock insider talking to a fellow tifoso over espresso. \
Use paragraph breaks to separate topics. Translate any Italian content \
into English seamlessly.

STEP 3 — RESPOND with a JSON object (not an array):

{
  "briefing": "The full narrative as one string. Use \\n\\n between paragraphs.",
  "source_links": [
    {"title": "Short descriptive title", "url": "original link"}
  ]
}

source_links should list every original article you drew from, in the \
order they appear in the narrative.

If NONE of the items are Ferrari-related, return:
{"briefing": "", "source_links": []}

No markdown fences. Only valid JSON."""


def _init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            hash TEXT PRIMARY KEY,
            title TEXT,
            source TEXT,
            ts TEXT
        )
    """)
    conn.commit()
    return conn


def _hash_item(title: str, link: str) -> str:
    return hashlib.sha256(f"{title}|{link}".encode()).hexdigest()[:16]


def _parse_entry_time(entry) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        tp = entry.get(field)
        if tp:
            try:
                return datetime(*tp[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def _poll_feeds(cutoff: datetime) -> list[dict]:
    items = []
    for feed_def in FEEDS:
        name = feed_def["name"]
        url = feed_def["url"]
        log.info("Polling %s …", name)
        try:
            parsed = feedparser.parse(url)
            if parsed.bozo and not parsed.entries:
                log.warning("Feed error for %s: %s", name, parsed.bozo_exception)
                continue
            for entry in parsed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                summary = entry.get("summary", entry.get("description", ""))
                if not title:
                    continue
                pub_time = _parse_entry_time(entry)
                if pub_time and pub_time < cutoff:
                    continue
                items.append({
                    "source": name,
                    "lang": feed_def["lang"],
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": entry.get("published", ""),
                })
        except Exception:
            log.exception("Failed to poll %s", name)
    return items


def _analyse_batch(items: list[dict], api_key: str, model: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    payload = [
        {"source": it["source"], "lang": it["lang"], "title": it["title"],
         "link": it["link"], "text": it["summary"][:1500]}
        for it in items
    ]
    try:
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": f"Analyse these items:\n\n{json.dumps(payload, ensure_ascii=False)}"}],
            system=SYSTEM_PROMPT,
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Direct JSON parse failed — attempting repair")
            raw_fixed = re.sub(
                r'("briefing":\s*")(.*?)("(?:\s*,|\s*\}))',
                lambda m: m.group(1) + m.group(2).replace("\n", "\\n").replace("\r", "") + m.group(3),
                raw,
                flags=re.DOTALL,
            )
            return json.loads(raw_fixed)
    except Exception:
        log.exception("Maranello analysis failed")
        return {"briefing": "", "source_links": []}


def run(api_key: str, db_path: Path, model: str = "claude-sonnet-4-6") -> dict:
    """
    Run the Maranello Signal pipeline.

    Args:
        api_key:   Anthropic API key
        db_path:   Path to the SQLite dedup database
        model:     Claude model ID

    Returns:
        {"briefing": "...", "source_links": [...]}
        briefing is "" if no Ferrari content found today.
    """
    log.info("=== Maranello Signal pipeline ===")

    now_et = datetime.now(ZoneInfo("America/New_York"))
    cutoff = (now_et - timedelta(hours=24)).astimezone(timezone.utc)
    log.info("Collecting Ferrari items since %s", cutoff.isoformat())

    conn = _init_db(db_path)
    try:
        raw = _poll_feeds(cutoff)
        unseen = []
        for item in raw:
            h = _hash_item(item["title"], item["link"])
            row = conn.execute("SELECT 1 FROM seen WHERE hash = ?", (h,)).fetchone()
            if not row:
                unseen.append(item)
                conn.execute(
                    "INSERT OR IGNORE INTO seen (hash, title, source, ts) VALUES (?, ?, ?, ?)",
                    (h, item["title"], item["source"], datetime.now(timezone.utc).isoformat()),
                )
        conn.commit()

        if not unseen:
            log.info("No new Ferrari items.")
            return {"briefing": "", "source_links": []}

        log.info("Processing %d new Maranello items …", len(unseen))

        if len(unseen) <= 30:
            result = _analyse_batch(unseen, api_key, model)
        else:
            paragraphs, all_links = [], []
            for i in range(0, len(unseen), 30):
                chunk_result = _analyse_batch(unseen[i:i + 30], api_key, model)
                if chunk_result.get("briefing"):
                    paragraphs.append(chunk_result["briefing"])
                    all_links.extend(chunk_result.get("source_links", []))
            result = {"briefing": "\n\n".join(paragraphs), "source_links": all_links}

        return result
    finally:
        conn.close()

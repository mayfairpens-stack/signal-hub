"""
RSS/Atom feed fetcher for blogs, Substack, and Medium.
"""

import feedparser
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass, field
import time
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ContentItem:
    """Represents a piece of content from any source."""
    id: str  # Unique identifier (URL or platform-specific ID)
    person_id: str  # Key from config (e.g., 'simon_willison')
    person_name: str  # Display name (e.g., 'Simon Willison')
    source: str  # Platform name (e.g., 'rss', 'youtube', 'twitter')
    source_name: str  # Specific source (e.g., 'Simon Willison's Blog')
    title: str
    content: str  # Main text content
    url: str
    published: datetime
    raw_html: str = ""  # Original HTML if available
    metadata: dict = field(default_factory=dict)

    def __hash__(self):
        return hash(self.id)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'person_id': self.person_id,
            'person_name': self.person_name,
            'source': self.source,
            'source_name': self.source_name,
            'title': self.title,
            'content': self.content,
            'url': self.url,
            'published': self.published.isoformat(),
            'metadata': self.metadata
        }


class RSSFetcher:
    """Fetches and parses RSS/Atom feeds."""

    def __init__(self, delay_seconds: float = 1.0):
        self.delay_seconds = delay_seconds
        self._last_request_time = 0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self._last_request_time = time.time()

    def _clean_html(self, html: str) -> str:
        if not html:
            return ""
        soup = BeautifulSoup(html, 'lxml')
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        text = soup.get_text(separator=' ')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _parse_date(self, entry: dict) -> Optional[datetime]:
        for field_name in ['published_parsed', 'updated_parsed', 'created_parsed']:
            if field_name in entry and entry[field_name]:
                try:
                    dt = datetime(*entry[field_name][:6])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except (TypeError, ValueError) as e:
                    logger.debug(f"Failed to parse date from {field_name}: {e}")
                    continue
        for field_name in ['published', 'updated', 'created']:
            if field_name in entry and entry[field_name]:
                try:
                    from dateutil import parser
                    dt = parser.parse(entry[field_name])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception as e:
                    logger.debug(f"Failed to parse date string from {field_name}: {e}")
                    continue
        return None

    def fetch_feed(
        self,
        feed_url: str,
        person_id: str,
        person_name: str,
        source_name: str,
        lookback_hours: int = 24
    ) -> list[ContentItem]:
        self._rate_limit()
        logger.info(f"Fetching RSS feed: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            logger.error(f"Failed to parse feed {feed_url}: {e}")
            return []

        if feed.bozo and feed.bozo_exception:
            logger.warning(f"Feed parse warning for {feed_url}: {feed.bozo_exception}")

        if not feed.entries:
            logger.info(f"No entries found in feed: {feed_url}")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        items = []
        for entry in feed.entries:
            pub_date = self._parse_date(entry)
            if not pub_date:
                logger.debug(f"Skipping entry without date: {entry.get('title', 'Unknown')}")
                continue
            if pub_date < cutoff:
                logger.debug(f"Skipping old entry: {entry.get('title', 'Unknown')} ({pub_date})")
                continue

            content_html = ""
            if 'content' in entry and entry.content:
                content_html = entry.content[0].get('value', '')
            elif 'summary' in entry:
                content_html = entry.summary
            elif 'description' in entry:
                content_html = entry.description

            content_text = self._clean_html(content_html)

            item = ContentItem(
                id=entry.get('id', entry.get('link', '')),
                person_id=person_id,
                person_name=person_name,
                source='rss',
                source_name=source_name,
                title=entry.get('title', 'Untitled'),
                content=content_text,
                url=entry.get('link', ''),
                published=pub_date,
                raw_html=content_html,
                metadata={
                    'author': entry.get('author', ''),
                    'tags': [tag.get('term', '') for tag in entry.get('tags', [])],
                }
            )
            items.append(item)
            logger.info(f"Found content: {item.title} ({item.published})")

        logger.info(f"Fetched {len(items)} items from {feed_url}")
        return items

    def fetch_all_feeds(
        self,
        people_config: dict,
        lookback_hours: int = 24
    ) -> list[ContentItem]:
        all_items = []
        for person_id, person_data in people_config.items():
            person_name = person_data.get('name', person_id)
            feeds = person_data.get('rss', [])
            person_lookback = person_data.get('lookback_hours', lookback_hours)
            if not feeds:
                continue
            for feed_config in feeds:
                feed_url = feed_config.get('url')
                feed_name = feed_config.get('name', 'Unknown Feed')
                if not feed_url:
                    continue
                try:
                    items = self.fetch_feed(
                        feed_url=feed_url,
                        person_id=person_id,
                        person_name=person_name,
                        source_name=feed_name,
                        lookback_hours=person_lookback
                    )
                    all_items.extend(items)
                except Exception as e:
                    logger.error(f"Error fetching feed for {person_name}: {e}")
                    continue
        all_items.sort(key=lambda x: x.published, reverse=True)
        return all_items

"""
Web search fetcher for discovering recent content via DuckDuckGo.

Useful for people who are active on platforms without reliable RSS feeds.
Searches the web for recent mentions and extracts content.
"""

import logging
import re
import time
from datetime import datetime, timezone

from dateutil import parser as dateutil_parser
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from .rss_fetcher import ContentItem

logger = logging.getLogger(__name__)


class WebFetcher:
    """Fetches recent content about a person via web search."""

    def __init__(self, delay_seconds: float = 1.0, fetch_timeout: int = 10):
        self.delay_seconds = delay_seconds
        self.fetch_timeout = fetch_timeout
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

    def _fetch_page_text(self, url: str) -> str:
        self._rate_limit()
        try:
            resp = requests.get(
                url,
                timeout=self.fetch_timeout,
                headers={'User-Agent': 'SignalHub/1.0 (digest bot)'}
            )
            resp.raise_for_status()
            return self._clean_html(resp.text)
        except Exception as e:
            logger.debug(f"Failed to fetch {url}: {e}")
            return ""

    def fetch_for_person(
        self,
        person_id: str,
        person_name: str,
        search_queries: list[str],
        max_results: int = 5,
    ) -> list[ContentItem]:
        items = []
        seen_urls: set[str] = set()

        for query in search_queries:
            logger.info(f"Web search: {query}")
            self._rate_limit()
            try:
                results = DDGS().news(query, max_results=max_results)
            except Exception as e:
                logger.error(f"Web search failed for '{query}': {e}")
                continue

            for result in results:
                url = result.get('url', '')
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title = result.get('title', 'Untitled')
                snippet = result.get('body', '')

                pub_date = datetime.now(timezone.utc)
                date_str = result.get('date', '')
                if date_str:
                    try:
                        pub_date = dateutil_parser.parse(date_str)
                        if pub_date.tzinfo is None:
                            pub_date = pub_date.replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        pass

                full_text = self._fetch_page_text(url)
                content = full_text if full_text else snippet
                if len(content) > 5000:
                    content = content[:5000]

                item = ContentItem(
                    id=url,
                    person_id=person_id,
                    person_name=person_name,
                    source='web_search',
                    source_name=f'Web Search: {query}',
                    title=title,
                    content=content,
                    url=url,
                    published=pub_date,
                    metadata={'search_query': query, 'snippet': snippet},
                )
                items.append(item)
                logger.info(f"Found web result: {title}")

        logger.info(f"Web search found {len(items)} items for {person_name}")
        return items

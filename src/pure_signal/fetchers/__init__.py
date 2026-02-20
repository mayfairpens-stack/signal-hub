# Content fetchers for various platforms
"""
Fetchers for extracting content from:
- RSS/Atom feeds (blogs, Substack, Medium)
- Web search (DuckDuckGo)
"""

from .rss_fetcher import RSSFetcher, ContentItem
from .web_fetcher import WebFetcher

__all__ = ['RSSFetcher', 'WebFetcher', 'ContentItem']

"""
Pure Signal pipeline — AI researcher intelligence.

Fetches RSS feeds and web search results for configured AI researchers,
deduplicates, and synthesizes a TTS-optimized narrative digest via Claude.

Returns the digest as a markdown string (does not build site or deploy).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from .fetchers.rss_fetcher import RSSFetcher, ContentItem
from .fetchers.web_fetcher import WebFetcher
from .dedup import DeduplicationStore
from .synthesizer import DigestSynthesizer

log = logging.getLogger(__name__)


def run(
    people_config: dict,
    api_key: str,
    dedup_path: Path,
    synthesis_model: str = "claude-sonnet-4-6",
    max_tokens: int = 8000,
    temperature: float = 0.7,
    lookback_hours: int = 24,
    rss_delay: float = 1.0,
) -> str:
    """
    Run the Pure Signal pipeline.

    Args:
        people_config:    Dict of people + sources from config.yaml
        api_key:          Anthropic API key
        dedup_path:       Path to the JSON deduplication store
        synthesis_model:  Claude model ID
        max_tokens:       Max tokens for synthesis response
        temperature:      Sampling temperature
        lookback_hours:   Global lookback window (per-person overrides in config)
        rss_delay:        Seconds to wait between RSS requests

    Returns:
        Markdown-formatted digest string, or "" if nothing to report.
    """
    log.info("=== Pure Signal pipeline ===")

    dedup = DeduplicationStore(str(dedup_path))
    rss_fetcher = RSSFetcher(delay_seconds=rss_delay)
    web_fetcher = WebFetcher(delay_seconds=1.0)

    all_items: list[ContentItem] = []

    # RSS feeds
    log.info("Fetching RSS content …")
    rss_items = rss_fetcher.fetch_all_feeds(people_config, lookback_hours)
    all_items.extend(rss_items)
    log.info("Found %d RSS items", len(rss_items))

    # Web search (for people with web_search config block)
    for person_id, person_data in people_config.items():
        ws_config = person_data.get("web_search")
        if not ws_config:
            continue
        person_name = person_data.get("name", person_id)
        queries = ws_config.get("queries", [])
        max_results = ws_config.get("max_results", 5)
        if not queries:
            continue
        log.info("Web search for %s …", person_name)
        try:
            ws_items = web_fetcher.fetch_for_person(
                person_id=person_id,
                person_name=person_name,
                search_queries=queries,
                max_results=max_results,
            )
            all_items.extend(ws_items)
        except Exception as e:
            log.error("Web search failed for %s: %s", person_name, e)

    all_items.sort(key=lambda x: x.published, reverse=True)

    if not all_items:
        log.info("No content found — quiet day for Pure Signal")
        return ""

    unprocessed = dedup.filter_unprocessed(all_items)
    if not unprocessed:
        log.info("All content already processed — quiet day for Pure Signal")
        return ""

    log.info("Synthesizing %d new Pure Signal items …", len(unprocessed))

    synthesizer = DigestSynthesizer(
        api_key=api_key,
        model=synthesis_model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    digest = synthesizer.synthesize(unprocessed)

    if digest:
        dedup.mark_batch_processed(
            [item.id for item in unprocessed],
            {"digest_date": datetime.now(timezone.utc).isoformat()},
        )

    return digest

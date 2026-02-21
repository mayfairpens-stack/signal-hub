"""
HN Signal pipeline — Hacker News daily digest.

Fetches top stories from the HN Algolia API, enriches with comments,
and synthesizes a morning digest via Claude.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.hn_signal.fetch import fetch_stories
from src.hn_signal.synthesize import synthesize

logger = logging.getLogger(__name__)

SEEN_IDS_MAX_AGE_DAYS = 7


def _load_seen_ids(path: Path) -> dict:
    """Load seen story IDs from disk."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to load seen IDs from %s: %s", path, e)
        return {}


def _save_seen_ids(seen: dict, path: Path) -> None:
    """Save seen story IDs to disk, pruning old entries."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=SEEN_IDS_MAX_AGE_DAYS)
    pruned = {}
    for sid, meta in seen.items():
        first_seen = meta.get("first_seen", "")
        try:
            dt = datetime.fromisoformat(first_seen)
            if dt > cutoff:
                pruned[sid] = meta
        except (ValueError, TypeError):
            pruned[sid] = meta

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pruned, indent=2), encoding="utf-8")
    logger.info("Saved %d seen IDs (pruned %d)", len(pruned), len(seen) - len(pruned))


def run(
    api_key: str,
    seen_ids_path: str | Path,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Run the HN Signal pipeline.

    Args:
        api_key:       Anthropic API key.
        seen_ids_path: Path to the seen-IDs JSON file.
        model:         Claude model ID.
        max_tokens:    Max synthesis tokens.
        temperature:   Sampling temperature.

    Returns:
        Markdown digest string, or "" if nothing new.
    """
    seen_path = Path(seen_ids_path)
    seen_ids = _load_seen_ids(seen_path)

    logger.info("HN Signal: fetching stories (seen=%d)...", len(seen_ids))
    stories = fetch_stories(seen_ids)

    if not stories:
        logger.info("HN Signal: no new stories — quiet day")
        return ""

    logger.info("HN Signal: synthesizing digest for %d stories...", len(stories))
    digest_md = synthesize(
        stories=stories,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=api_key,
    )

    # Update seen IDs
    now_iso = datetime.now(timezone.utc).isoformat()
    for s in stories:
        sid = str(s["id"])
        seen_ids[sid] = {
            "first_seen": seen_ids.get(sid, {}).get("first_seen", now_iso),
            "num_comments": s.get("num_comments", 0),
        }
    _save_seen_ids(seen_ids, seen_path)

    return digest_md

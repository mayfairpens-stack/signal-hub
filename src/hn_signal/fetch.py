"""HN Algolia API data fetching."""

import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

# Constants
HN_ALGOLIA_FRONT_PAGE = "https://hn.algolia.com/api/v1/search_by_date?tags=front_page&hitsPerPage=60"
HN_ALGOLIA_ITEM = "https://hn.algolia.com/api/v1/items/{id}"
TOP_STORIES_COUNT = 15
COMMENTS_PER_STORY = 15
FRESHNESS_HOURS = 18
STALE_HOURS = 20
STALE_COMMENT_RATIO = 0.5


def fetch_front_page() -> list[dict]:
    """Fetch current front page stories from HN Algolia API."""
    logger.info("Fetching front page stories...")
    resp = requests.get(HN_ALGOLIA_FRONT_PAGE, timeout=30)
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    logger.info("Fetched %d front page stories", len(hits))
    return hits


def score_story(story: dict) -> float:
    """Score a story by points + comment count for ranking."""
    points = story.get("points") or 0
    comments = story.get("num_comments") or 0
    return points + comments * 1.5


def is_fresh(story: dict, now: datetime) -> bool:
    """Check if a story passes the freshness filter."""
    created = story.get("created_at")
    if not created:
        return True
    try:
        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True

    age_hours = (now - created_dt).total_seconds() / 3600
    if age_hours < FRESHNESS_HOURS:
        return True
    if age_hours < STALE_HOURS:
        return True

    # Stale stories only if high comment-to-upvote ratio
    points = story.get("points") or 1
    comments = story.get("num_comments") or 0
    return (comments / points) > STALE_COMMENT_RATIO


def extract_comments(children: list[dict], limit: int) -> list[dict]:
    """Extract top comments from a nested comment tree (breadth-first)."""
    comments = []
    queue = list(children or [])
    while queue and len(comments) < limit:
        child = queue.pop(0)
        if child.get("text") and child.get("author"):
            comments.append({
                "author": child["author"],
                "text": child["text"][:500],
            })
        queue.extend(child.get("children") or [])
    return comments


def fetch_story_comments(story_id: int) -> list[dict]:
    """Fetch the comment tree for a specific story."""
    url = HN_ALGOLIA_ITEM.format(id=story_id)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return extract_comments(data.get("children", []), COMMENTS_PER_STORY)
    except requests.RequestException as e:
        logger.warning("Failed to fetch comments for story %s: %s", story_id, e)
        return []


def fetch_stories(seen_ids: dict | None = None) -> list[dict]:
    """Fetch, filter, rank, and enrich top HN stories.

    Args:
        seen_ids: dict mapping story ID strings to metadata dicts
                  with keys 'first_seen' and 'num_comments'.

    Returns:
        List of story dicts ready for synthesis.
    """
    seen_ids = seen_ids or {}
    now = datetime.now(timezone.utc)

    hits = fetch_front_page()

    # Apply freshness filter
    fresh = [s for s in hits if is_fresh(s, now)]
    logger.info("%d stories pass freshness filter", len(fresh))

    # Separate new vs update stories
    new_stories = []
    update_stories = []
    for s in fresh:
        sid = str(s.get("objectID", ""))
        if sid in seen_ids:
            prev = seen_ids[sid]
            prev_comments = prev.get("num_comments", 0)
            curr_comments = s.get("num_comments") or 0
            if prev_comments > 0 and curr_comments >= prev_comments * 2:
                s["_update"] = True
                update_stories.append(s)
        else:
            new_stories.append(s)

    # Rank by score and take top N
    new_stories.sort(key=score_story, reverse=True)
    selected = new_stories[:TOP_STORIES_COUNT]

    # Add update stories (they always get included)
    selected.extend(update_stories)
    logger.info("Selected %d stories (%d updates)", len(selected), len(update_stories))

    # Fetch comments for selected stories
    enriched = []
    for s in selected:
        story_id = s.get("objectID")
        if not story_id:
            continue

        comments = fetch_story_comments(story_id)
        enriched.append({
            "id": story_id,
            "title": s.get("title", ""),
            "url": s.get("url", ""),
            "points": s.get("points", 0),
            "num_comments": s.get("num_comments", 0),
            "author": s.get("author", ""),
            "created_at": s.get("created_at", ""),
            "update": s.get("_update", False),
            "comments": comments,
        })

    logger.info("Enriched %d stories with comments", len(enriched))
    return enriched

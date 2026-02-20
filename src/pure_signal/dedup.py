"""
Deduplication system for tracking processed Pure Signal content.
Uses a JSON file as the backing store.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DeduplicationStore:
    """Tracks processed content to avoid duplicates."""

    def __init__(self, store_path: str = "data/pure_signal_processed.json"):
        self.store_path = Path(store_path)
        self._ensure_store_exists()
        self._data = self._load()

    def _ensure_store_exists(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self._save({'processed': {}, 'metadata': {'created': datetime.now(timezone.utc).isoformat()}})

    def _load(self) -> dict:
        try:
            with open(self.store_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to load store, creating new: {e}")
            return {'processed': {}, 'metadata': {'created': datetime.now(timezone.utc).isoformat()}}

    def _save(self, data: Optional[dict] = None):
        if data is None:
            data = self._data
        data['metadata']['last_updated'] = datetime.now(timezone.utc).isoformat()
        with open(self.store_path, 'w') as f:
            json.dump(data, f, indent=2)

    def is_processed(self, content_id: str) -> bool:
        return content_id in self._data.get('processed', {})

    def mark_processed(self, content_id: str, metadata: Optional[dict] = None):
        if 'processed' not in self._data:
            self._data['processed'] = {}
        self._data['processed'][content_id] = {
            'processed_at': datetime.now(timezone.utc).isoformat(),
            'metadata': metadata or {}
        }
        self._save()

    def mark_batch_processed(self, content_ids: list[str], metadata: Optional[dict] = None):
        if 'processed' not in self._data:
            self._data['processed'] = {}
        timestamp = datetime.now(timezone.utc).isoformat()
        for content_id in content_ids:
            self._data['processed'][content_id] = {
                'processed_at': timestamp,
                'metadata': metadata or {}
            }
        self._save()
        logger.info(f"Marked {len(content_ids)} items as processed")

    def filter_unprocessed(self, items: list) -> list:
        unprocessed = [item for item in items if not self.is_processed(item.id)]
        logger.info(f"Filtered {len(items)} items to {len(unprocessed)} unprocessed")
        return unprocessed

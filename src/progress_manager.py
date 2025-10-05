"""
Progress tracking module for managing processed papers.

Handles:
- Tracking which papers have been processed
- Preventing duplicate processing
- Progress file backup and recovery
- Automatic cleanup of old records
"""

import json
import shutil
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ProgressManager:
    """
    Manages progress tracking for paper processing.

    Features:
    - Atomic writes to prevent corruption
    - Automatic backup rotation
    - Recovery from corrupted files
    - Retention policy for old records
    """
    def __init__(self, file_path: str, backup_count: int = 5, retention_days: int = 90):
        self.file_path = file_path
        self.backup_count = backup_count
        self.retention_days = retention_days
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.file_path):
            self._data = {}
            return
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load progress file, attempting recovery: {e}")
            self._recover_from_backup()

    def _recover_from_backup(self):
        dir_path = os.path.dirname(self.file_path)
        base = os.path.basename(self.file_path)
        backups = [f for f in os.listdir(dir_path) if f.startswith(base + '.')]
        backups.sort(reverse=True)
        for b in backups:
            try:
                with open(os.path.join(dir_path, b), 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                    logger.info(f"Recovered progress from backup {b}")
                    return
            except Exception:
                continue
        self._data = {}

    def _rotate_backups(self):
        dir_path = os.path.dirname(self.file_path)
        base = os.path.basename(self.file_path)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        backup_name = f"{base}.{timestamp}.bak"
        shutil.copy2(self.file_path, os.path.join(dir_path, backup_name))
        backups = [f for f in os.listdir(dir_path) if f.startswith(base + '.')]
        backups.sort(reverse=True)
        for old in backups[self.backup_count:]:
            try:
                os.remove(os.path.join(dir_path, old))
            except OSError:
                pass

    def save(self) -> None:
        temp_path = self.file_path + '.tmp'
        try:
            if os.path.exists(self.file_path):
                self._rotate_backups()
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.file_path)
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def is_processed(self, journal: str, paper_id: str) -> bool:
        j = self._data.get(journal, {})
        return paper_id in j.get('processed_ids', [])

    def add_processed(self, journal: str, paper_id: str) -> None:
        j = self._data.setdefault(journal, {
            'last_processed': None,
            'processed_ids': [],
            'last_success': None,
            'error_count': 0
        })
        if paper_id not in j['processed_ids']:
            j['processed_ids'].append(paper_id)
        j['last_processed'] = datetime.now().isoformat()
        j['last_success'] = datetime.now().isoformat()

    def cleanup(self):
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        for journal, info in list(self._data.items()):
            processed = info.get('processed_ids', [])
            # simple retention: keep last 100 ids (configurable if needed)
            if len(processed) > 500:
                info['processed_ids'] = processed[-500:]
            # remove journal if no activity beyond retention
            last = info.get('last_processed')
            if last:
                try:
                    dt = datetime.fromisoformat(last)
                    if dt < cutoff:
                        logger.info(f"Removing stale journal progress: {journal}")
                        del self._data[journal]
                except ValueError:
                    continue

    def get_state(self) -> Dict[str, Any]:
        return self._data

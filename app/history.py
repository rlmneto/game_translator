"""Translation history — stores and exports past translations."""

import csv
import json
import logging
import os
import time

from .config import BASE_DIR

logger = logging.getLogger(__name__)

HISTORY_FILE = os.path.join(BASE_DIR, "translation_history.json")
MAX_HISTORY = 200


class TranslationHistory:
    def __init__(self):
        self._entries: list[dict] = []
        self._load()

    # -- public API ------------------------------------------------------

    def add(self, original: str, corrected: str, translation: str,
            source_lang: str, target_lang: str, model: str):
        entry = {
            "timestamp": time.time(),
            "original": original,
            "corrected": corrected,
            "translation": translation,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "model": model,
        }
        self._entries.append(entry)
        if len(self._entries) > MAX_HISTORY:
            self._entries = self._entries[-MAX_HISTORY:]
        self._save()
        logger.info("History entry added (%d total)", len(self._entries))

    @property
    def entries(self) -> list[dict]:
        """Most recent first."""
        return list(reversed(self._entries))

    @property
    def count(self) -> int:
        return len(self._entries)

    def clear(self):
        self._entries.clear()
        self._save()
        logger.info("History cleared")

    # -- export ----------------------------------------------------------

    def export_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, ensure_ascii=False, indent=2)
        logger.info("Exported %d entries to JSON: %s", len(self._entries), path)

    def export_csv(self, path: str):
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "source_lang", "target_lang",
                "model", "original", "corrected", "translation",
            ])
            for e in self._entries:
                writer.writerow([
                    time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(e["timestamp"])
                    ),
                    e["source_lang"], e["target_lang"], e["model"],
                    e["original"], e["corrected"], e["translation"],
                ])
        logger.info("Exported %d entries to CSV: %s", len(self._entries), path)

    # -- persistence -----------------------------------------------------

    def _load(self):
        if not os.path.exists(HISTORY_FILE):
            return
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                self._entries = json.load(f)
            logger.info("Loaded %d history entries", len(self._entries))
        except Exception as exc:
            logger.warning("Failed to load history: %s", exc)
            self._entries = []

    def _save(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to save history: %s", exc)

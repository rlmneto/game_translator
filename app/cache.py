"""Translation cache — avoid re-translating identical texts."""

import hashlib
import json
import logging
import os
import time

from .config import BASE_DIR

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(BASE_DIR, "translation_cache.json")
MAX_CACHE_SIZE = 500


class TranslationCache:
    """LRU-like cache for translations, persisted to disk."""

    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._load()

    # -- public API ------------------------------------------------------

    def get(self, text: str, source_lang: str, target_lang: str,
            model: str) -> tuple[str, str] | None:
        key = self._make_key(text, source_lang, target_lang, model)
        entry = self._cache.get(key)
        if entry:
            entry["hits"] += 1
            entry["last_used"] = time.time()
            logger.debug("Cache HIT  key=%s", key)
            return entry["corrected"], entry["translation"]
        logger.debug("Cache MISS key=%s", key)
        return None

    def put(self, text: str, source_lang: str, target_lang: str,
            model: str, corrected: str, translation: str):
        key = self._make_key(text, source_lang, target_lang, model)
        self._cache[key] = {
            "original": text,
            "corrected": corrected,
            "translation": translation,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "model": model,
            "hits": 1,
            "created": time.time(),
            "last_used": time.time(),
        }
        self._evict()
        self._save()
        logger.debug("Cached translation key=%s", key)

    def clear(self):
        self._cache.clear()
        self._save()
        logger.info("Translation cache cleared")

    @property
    def size(self) -> int:
        return len(self._cache)

    # -- internals -------------------------------------------------------

    @staticmethod
    def _make_key(text: str, src: str, tgt: str, model: str) -> str:
        raw = f"{text}|{src}|{tgt}|{model}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _evict(self):
        if len(self._cache) <= MAX_CACHE_SIZE:
            return
        sorted_keys = sorted(
            self._cache, key=lambda k: self._cache[k]["last_used"]
        )
        for k in sorted_keys[: len(self._cache) - MAX_CACHE_SIZE]:
            del self._cache[k]
        logger.info("Evicted cache entries, now %d", len(self._cache))

    def _load(self):
        if not os.path.exists(CACHE_FILE):
            return
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
            logger.info("Loaded %d cached translations", len(self._cache))
        except Exception as exc:
            logger.warning("Failed to load cache: %s", exc)
            self._cache = {}

    def _save(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to save cache: %s", exc)

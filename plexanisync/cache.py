# coding=utf-8
import atexit
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from plexanisync.logger_adapter import PrefixLoggerAdapter

logger = PrefixLoggerAdapter(logging.getLogger("PlexAniSync"), {"prefix": "CACHE"})

# Bump this when the stored data format changes, so old cache files are ignored
CACHE_FORMAT_VERSION = 1


class FileCache:
    """
    Small key/value cache persisted as a JSON file.

    File layout: {"version": 1, "entries": {key: {"timestamp": <unix seconds>, "value": <json data>}}}
    Entries older than ttl_seconds are treated as missing and dropped on the next save.
    The file is only written once when the program exits (or when save() is called),
    because rewriting the whole file after every single lookup would be slow.
    """

    def __init__(self, file_path: str, ttl_seconds: int):
        self.file_path = file_path
        self.ttl_seconds = ttl_seconds
        self.entries: Dict[str, Dict[str, Any]] = {}
        self.dirty = False
        self.__load()
        atexit.register(self.save)

    def get(self, key: str) -> Optional[Any]:
        entry = self.entries.get(key)
        if entry is None:
            return None
        if self.__is_expired(entry):
            del self.entries[key]
            self.dirty = True
            return None
        return entry["value"]

    def put(self, key: str, value: Any):
        self.entries[key] = {"timestamp": time.time(), "value": value}
        self.dirty = True

    def save(self):
        if not self.dirty:
            return
        self.entries = {key: entry for key, entry in self.entries.items() if not self.__is_expired(entry)}
        temp_path = f"{self.file_path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as cache_file:
                json.dump({"version": CACHE_FORMAT_VERSION, "entries": self.entries}, cache_file)
            # atomic replace so a crash can't leave a half written cache file behind
            os.replace(temp_path, self.file_path)
            self.dirty = False
        except Exception as exception:
            logger.warning(f"Failed to write cache file {self.file_path}: {exception}")

    def __is_expired(self, entry: Dict[str, Any]) -> bool:
        return time.time() - entry["timestamp"] > self.ttl_seconds

    def __load(self):
        if not os.path.isfile(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as cache_file:
                data = json.load(cache_file)
            if data.get("version") != CACHE_FORMAT_VERSION:
                logger.info("Cache file has a different format version, starting with an empty cache")
                return
            self.entries = data["entries"]
        except Exception as exception:
            logger.warning(f"Failed to read cache file {self.file_path}, starting empty: {exception}")
            self.entries = {}

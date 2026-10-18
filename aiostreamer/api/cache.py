import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path

log = logging.getLogger("aiostreamer.cache")

MAX_AGE = 30 * 24 * 3600
MEMORY_ITEMS = 300


class _Flight:
    def __init__(self):
        self.event = threading.Event()
        self.value = None
        self.error = None


class JsonCache:
    def __init__(self, root, clock=time.time, memory_items=MEMORY_ITEMS):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._limit = memory_items
        self._memory = OrderedDict()
        self._lock = threading.Lock()
        self._inflight = {}

    def _path(self, key):
        return self.root / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def _remember(self, key, entry):
        with self._lock:
            self._memory[key] = entry
            self._memory.move_to_end(key)
            while len(self._memory) > self._limit:
                self._memory.popitem(last=False)

    def peek(self, key):
        with self._lock:
            entry = self._memory.get(key)
            if entry is not None:
                self._memory.move_to_end(key)
                return entry
        try:
            data = json.loads(self._path(key).read_text())
            entry = (float(data["t"]), data["v"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        self._remember(key, entry)
        return entry

    def put(self, key, value):
        entry = (self._clock(), value)
        self._remember(key, entry)
        path = self._path(key)
        tmp = path.with_suffix(".part%d" % threading.get_ident())
        try:
            tmp.write_text(json.dumps({"t": entry[0], "v": value}))
            os.replace(tmp, path)
        except OSError as exc:
            log.debug("cache write failed: %s", exc)
            tmp.unlink(missing_ok=True)

    def get(self, key, ttl, fetch):
        hit = self.peek(key)
        if hit is not None and self._clock() - hit[0] < ttl:
            return hit[1]
        try:
            return self._single(key, fetch)
        except Exception:
            if hit is not None:
                log.info("serving stale %s", key[-60:])
                return hit[1]
            raise

    def _single(self, key, fetch):
        with self._lock:
            flight = self._inflight.get(key)
            owner = flight is None
            if owner:
                flight = self._inflight[key] = _Flight()
        if not owner:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            return flight.value
        try:
            flight.value = fetch()
            self.put(key, flight.value)
            return flight.value
        except Exception as exc:
            flight.error = exc
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            flight.event.set()

    def drop(self, key):
        with self._lock:
            self._memory.pop(key, None)
        self._path(key).unlink(missing_ok=True)

    def clear(self):
        with self._lock:
            self._memory.clear()
        for path in self.root.glob("*.json"):
            path.unlink(missing_ok=True)

    def prune(self, max_age=MAX_AGE):
        now = self._clock()
        try:
            files = list(self.root.iterdir())
        except OSError:
            return
        for path in files:
            try:
                if now - path.stat().st_mtime > (3600 if ".part" in path.name else max_age):
                    path.unlink(missing_ok=True)
            except OSError:
                pass

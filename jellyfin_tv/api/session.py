import hashlib
import json
import logging
import os
import threading

import keyring

from jellyfin_tv.api.aio import AioClient, AioError, instance_origin, manifest_uuid, normalize_manifest_url, resolve_manifest
from jellyfin_tv.api.cache import JsonCache
from jellyfin_tv.api.history import WatchState
from jellyfin_tv.models.settings import cache_dir, config_dir

log = logging.getLogger("jellyfin_tv.session")

KEYRING_SERVICE = "jellyfin-tv"
KEYRING_KEY = "aiostreams"


class LoginError(Exception):
    pass


def account_key(manifest_url):
    return hashlib.sha1((manifest_uuid(manifest_url) or manifest_url).encode()).hexdigest()[:16]


def display_name(user, manifest_url):
    name = (user or "").strip() or manifest_uuid(manifest_url)
    if len(name) == 36 and name.count("-") == 4:
        return name[:8]
    return name or instance_origin(manifest_url)


def clean_store(data):
    if not isinstance(data, dict):
        return {"active": "", "accounts": []}
    accounts = [a for a in data.get("accounts") or [] if isinstance(a, dict) and a.get("manifest") and a.get("key")]
    return {"active": data.get("active", ""), "accounts": accounts}


class Session:
    def __init__(self, settings, resolver=resolve_manifest, client_factory=None):
        self.settings = settings
        self.client = None
        self.history = None
        self.account = {}
        self._resolver = resolver
        self._client_factory = client_factory or self._make_client

    @staticmethod
    def _make_client(manifest, key):
        return AioClient(manifest, JsonCache(cache_dir() / "aio" / key))

    @property
    def logged_in(self):
        return self.client is not None

    @property
    def username(self):
        return self.account.get("name", "")

    @property
    def server(self):
        return self.account.get("instance", "")

    def login(self, instance, user, password):
        text = (instance or "").strip()
        if not text:
            raise LoginError("Enter your AIOStreams address or manifest URL")
        try:
            if "manifest.json" in text or text.startswith("stremio://"):
                manifest = normalize_manifest_url(text)
            else:
                if not (user or "").strip():
                    raise LoginError("Enter your UUID or alias and password")
                manifest = self._resolver(text, user.strip(), password)
        except AioError as exc:
            raise LoginError(str(exc))
        key = account_key(manifest)
        client = self._client_factory(manifest, key)
        try:
            client.manifest(fresh=True)
        except AioError as exc:
            raise LoginError(str(exc))
        account = {"key": key, "manifest": manifest, "name": display_name(user, manifest), "instance": instance_origin(manifest),
                   "user": (user or "").strip() or manifest_uuid(manifest)}
        self._activate(account, client)
        store = self._load_store()
        store["accounts"] = [a for a in store["accounts"] if a.get("key") != key] + [account]
        store["active"] = key
        self._write_store(store)

    def accounts(self):
        store = self._load_store()
        return [{
            "key": a["key"],
            "server": a.get("instance", ""),
            "username": a.get("name", ""),
            "active": self.logged_in and a["key"] == self.account.get("key"),
        } for a in store["accounts"]]

    def switch(self, key):
        store = self._load_store()
        account = next((a for a in store["accounts"] if a.get("key") == key), None)
        if account is None:
            raise LoginError("Account not found")
        self._restore_account(account)
        store["active"] = key
        self._write_store(store)
        return True

    def restore(self):
        store = self._load_store()
        account = next((a for a in store["accounts"] if a.get("key") == store["active"]), None)
        return bool(account) and self._restore_account(account)

    def _restore_account(self, account):
        client = self._client_factory(account["manifest"], account["key"])
        try:
            client.manifest()
        except AioError as exc:
            if client.peek_manifest() is None:
                log.warning("saved account unusable: %s", exc)
                raise LoginError("Could not reach AIOStreams: %s" % exc)
        self._activate(account, client)
        return True

    def logout(self):
        store = self._load_store()
        key = self.account.get("key")
        store["accounts"] = [a for a in store["accounts"] if a.get("key") != key]
        store["active"] = ""
        self._write_store(store)
        self._teardown()

    def _activate(self, account, client):
        self.account = dict(account)
        self.client = client
        self.history = WatchState(config_dir() / "state" / ("%s.json" % account["key"]))
        threading.Thread(target=client.cache.prune, name="jftv-cache-prune", daemon=True).start()
        self.settings.set("server", account.get("instance", ""))
        self.settings.set("username", account.get("user") or account.get("name", ""))

    def _teardown(self):
        self.client = None
        self.history = None
        self.account = {}

    def clear_cache(self):
        if self.client is not None:
            self.client.cache.clear()

    @staticmethod
    def _fallback_path():
        return config_dir() / "accounts.json"

    def _read_stored(self):
        try:
            raw = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
            if raw:
                return raw
        except Exception as exc:
            log.warning("keyring unavailable: %s", exc)
        try:
            return self._fallback_path().read_text()
        except OSError:
            return None

    def _write_stored(self, raw):
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, raw)
            self._fallback_path().unlink(missing_ok=True)
            return
        except Exception as exc:
            log.warning("keyring unavailable, storing accounts in config dir: %s", exc)
        path = self._fallback_path()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write(raw)

    def _clear_stored(self):
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_KEY)
        except Exception:
            pass
        self._fallback_path().unlink(missing_ok=True)

    def _load_store(self):
        raw = self._read_stored()
        try:
            return clean_store(json.loads(raw) if raw else None)
        except ValueError:
            return clean_store(None)

    def _write_store(self, store):
        if store["accounts"]:
            self._write_stored(json.dumps(store))
        else:
            self._clear_stored()

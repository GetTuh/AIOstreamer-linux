import json
import logging
import os
import urllib.parse

import keyring
import requests
from jellyfin_tv import __version__
from jellyfin_tv.api.client import ApiClient
from jellyfin_tv.models.settings import config_dir

log = logging.getLogger("jellyfin_tv.session")

APP_NAME = "Jellyfin TV"
KEYRING_SERVICE = "jellyfin-tv"
KEYRING_KEY = "session"


PUBLIC_INFO = "/System/Info/Public"


class LoginError(Exception):
    pass


def account_key(server, user_id):
    return "%s|%s" % (server, user_id)


def migrate_store(data):
    if not isinstance(data, dict):
        return {"active": "", "accounts": []}
    if "accounts" in data:
        return {"active": data.get("active", ""), "accounts": [a for a in data["accounts"] if a.get("token")]}
    if data.get("token"):
        return {"active": account_key(data["server"], data["user_id"]), "accounts": [data]}
    return {"active": "", "accounts": []}


def normalize_server(url):
    url = (url or "").strip().rstrip("/")
    if url and "://" not in url:
        url = "http://" + url
    return url


def server_base(url):
    if url and url.endswith(PUBLIC_INFO):
        return url[:-len(PUBLIC_INFO)].rstrip("/")
    return ""


def same_origin(a, b):
    def origin(url):
        p = urllib.parse.urlsplit(url)
        port = p.port or {"http": 80, "https": 443}.get(p.scheme)
        return p.scheme.lower(), (p.hostname or "").lower(), port

    try:
        return origin(a) == origin(b)
    except ValueError:
        return False


class Session:
    def __init__(self, settings):
        self.settings = settings
        self.client = None
        self.server = ""
        self.user_id = ""
        self.username = ""
        self.token = ""
        self._quick = None
        self._http = None

    def http(self):
        if self._http is None:
            self._http = requests.Session()
        return self._http

    @property
    def logged_in(self):
        return self.client is not None

    def auth_header(self, with_token=True):
        parts = {
            "Client": APP_NAME,
            "Device": self.settings.device_name,
            "DeviceId": self.settings.device_id,
            "Version": __version__,
        }
        if self.token and with_token:
            parts["Token"] = self.token
        return "MediaBrowser " + ", ".join('%s="%s"' % (k, v) for k, v in parts.items())

    def _connect(self, server):
        server = normalize_server(server)
        if not server:
            raise LoginError("Server is required")
        try:
            resp = requests.get(server + PUBLIC_INFO, headers={"Authorization": self.auth_header(False)}, timeout=15)
            resp.raise_for_status()
            info = resp.json()
        except (requests.RequestException, ValueError) as exc:
            log.info("connect %s: %s", server, exc)
            raise LoginError("Server not reachable")
        if not isinstance(info, dict) or not info.get("Id"):
            raise LoginError("Server not reachable")
        return server_base(resp.url) or server

    def _switch_to(self, address, result, fallback_name=""):
        self._teardown()
        self._activate(address, result["User"]["Id"], result["AccessToken"], result["User"].get("Name") or fallback_name)
        self._save()

    def login(self, server, username, password):
        if not normalize_server(server) or not username:
            raise LoginError("Server and username are required")
        address = self._connect(server)
        try:
            result = self._post_anon(address, "Users/AuthenticateByName", json={"Username": username, "Pw": password or ""})
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (400, 401, 403):
                raise LoginError("Wrong username or password")
            raise
        if "AccessToken" not in result:
            raise LoginError("Wrong username or password")
        self._switch_to(address, result, username)

    def _post_anon(self, server, path, **kwargs):
        resp = requests.post(server + "/" + path, headers={"Authorization": self.auth_header(False)}, timeout=15, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def quick_connect_start(self, server):
        address = self._connect(server)
        try:
            data = self._post_anon(address, "QuickConnect/Initiate")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise LoginError("Quick Connect is disabled on this server")
            raise
        if not data.get("Secret") or not data.get("Code"):
            raise LoginError("Quick Connect is not available on this server")
        self._quick = {"server": address, "secret": data["Secret"], "code": data["Code"]}
        return data["Code"]

    def quick_connect_poll(self):
        quick = self._quick
        if not quick:
            return False
        resp = requests.get(quick["server"] + "/QuickConnect/Connect", params={"secret": quick["secret"]},
                            headers={"Authorization": self.auth_header(False)}, timeout=15)
        resp.raise_for_status()
        if not resp.json().get("Authenticated"):
            return False
        result = self._post_anon(quick["server"], "Users/AuthenticateWithQuickConnect", json={"Secret": quick["secret"]})
        if "AccessToken" not in result:
            raise LoginError("Quick Connect was not accepted")
        self._quick = None
        self._switch_to(quick["server"], result)
        return True

    def quick_connect_cancel(self):
        self._quick = None

    def accounts(self):
        store = self._load_store()
        return [{
            "key": account_key(a["server"], a["user_id"]),
            "server": a["server"],
            "username": a.get("username", ""),
            "active": self.logged_in and account_key(a["server"], a["user_id"]) == account_key(self.server, self.user_id),
        } for a in store["accounts"]]

    def switch(self, key):
        store = self._load_store()
        account = next((a for a in store["accounts"] if account_key(a["server"], a["user_id"]) == key), None)
        if account is None:
            raise LoginError("Account not found")
        self._teardown()
        store["active"] = key
        self._write_store(store)
        if not self._restore_account(account):
            raise LoginError("Sign in again: the saved login for %s expired" % (account.get("username") or account["server"]))
        return True

    @staticmethod
    def _fallback_path():
        return config_dir() / "session.json"

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
            log.warning("keyring unavailable, storing token in config dir: %s", exc)
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
            return migrate_store(json.loads(raw) if raw else None)
        except ValueError:
            return migrate_store(None)

    def _write_store(self, store):
        if store["accounts"]:
            self._write_stored(json.dumps(store))
        else:
            self._clear_stored()

    def restore(self):
        store = self._load_store()
        account = next((a for a in store["accounts"] if account_key(a["server"], a["user_id"]) == store["active"]), None)
        return bool(account) and self._restore_account(account)

    def _restore_account(self, data):
        self._activate(data["server"], data["user_id"], data["token"], data.get("username", ""))
        try:
            me = self.client.get("Users/Me")
        except Exception as exc:
            log.warning("saved session rejected: %s", exc)
            self._teardown()
            return False
        self.username = me.get("Name", self.username)
        return True

    def logout(self):
        if self.client:
            try:
                self.client.post("Sessions/Logout")
            except Exception:
                pass
        store = self._load_store()
        current = account_key(self.server, self.user_id)
        store["accounts"] = [a for a in store["accounts"] if account_key(a["server"], a["user_id"]) != current]
        store["active"] = ""
        self._teardown()
        self._write_store(store)

    def _activate(self, server, user_id, token, username):
        self.server = server
        self.user_id = user_id
        self.token = token
        self.client = ApiClient(server, self.auth_header, user_id)
        self.username = username
        self.settings.set("server", server)
        self.settings.set("username", username)
        try:
            self.client.post("Sessions/Capabilities/Full", json={
                "PlayableMediaTypes": ["Video"],
                "SupportsMediaControl": False,
                "SupportedCommands": [],
            })
        except Exception as exc:
            log.debug("capabilities not posted: %s", exc)

    def _teardown(self):
        if self.client:
            self.client.close()
        self.client = None
        self.token = ""
        self.user_id = ""

    def _save(self):
        store = self._load_store()
        key = account_key(self.server, self.user_id)
        data = {"server": self.server, "user_id": self.user_id, "token": self.token, "username": self.username}
        store["accounts"] = [a for a in store["accounts"] if account_key(a["server"], a["user_id"]) != key] + [data]
        store["active"] = key
        self._write_store(store)

    def url(self, path, **params):
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        return "%s/%s%s" % (self.server, path.lstrip("/"), "?" + query if query else "")

import requests

TIMEOUT = 30
USER_ID = "{UserId}"


class ApiClient:
    def __init__(self, server, auth_header, user_id="", http=None, timeout=TIMEOUT):
        self.server = server.rstrip("/")
        self.user_id = user_id
        self._auth_header = auth_header
        self._http = http or requests.Session()
        self._timeout = timeout

    def _fill(self, value):
        if isinstance(value, str):
            return value.replace(USER_ID, self.user_id)
        if isinstance(value, dict):
            return {k: self._fill(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._fill(v) for v in value]
        return value

    def request(self, method, path, params=None, json=None):
        resp = self._http.request(
            method,
            "%s/%s" % (self.server, self._fill(path).lstrip("/")),
            params=self._fill(params),
            json=self._fill(json),
            headers={"Authorization": self._auth_header(), "Accept": "application/json"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {}

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, json=None, params=None):
        return self.request("POST", path, params=params, json=json)

    def delete(self, path, params=None):
        return self.request("DELETE", path, params=params)

    def playback_info(self, item_id, profile, source_id=None):
        body = {"UserId": USER_ID, "DeviceProfile": profile, "AutoOpenLiveStream": True, "IsPlayback": True}
        if source_id:
            body["MediaSourceId"] = source_id
        return self.post("Items/%s/PlaybackInfo" % item_id, json=body)

    def close(self):
        self._http.close()

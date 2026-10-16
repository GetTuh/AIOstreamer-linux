import shutil
import threading
import unittest

from jellyfin_tv.tests.helpers import FakeSettings
from jellyfin_tv.api.client import ApiClient
from jellyfin_tv.api.session import LoginError, Session, server_base
from jellyfin_tv.player.mpv_ipc import MpvError, MpvIpc, command_line
from jellyfin_tv.player.reporter import PlaybackReporter


class FakeResponse:
    def __init__(self, data=None, status=200, url=""):
        self.data = data
        self.status_code = status
        self.url = url
        self.content = b"" if data is None else b"x"

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)

    def json(self):
        return self.data


class FakeHttp:
    def __init__(self, data=None):
        self.calls = []
        self.data = data

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return FakeResponse(self.data)

    def close(self):
        pass


class ApiClientTest(unittest.TestCase):
    def test_user_id_filled_everywhere(self):
        http = FakeHttp({"Items": []})
        client = ApiClient("http://srv/", lambda: "MediaBrowser Token=t", "u1", http)
        self.assertEqual(client.get("Users/{UserId}/Views", {"UserId": "{UserId}", "Limit": 3}), {"Items": []})
        method, url, kwargs = http.calls[0]
        self.assertEqual((method, url), ("GET", "http://srv/Users/u1/Views"))
        self.assertEqual(kwargs["params"], {"UserId": "u1", "Limit": 3})
        self.assertEqual(kwargs["headers"]["Authorization"], "MediaBrowser Token=t")

    def test_playback_info_body(self):
        http = FakeHttp()
        client = ApiClient("http://srv", lambda: "h", "u1", http)
        self.assertEqual(client.playback_info("i", {"Name": "p"}, "src"), {})
        method, url, kwargs = http.calls[0]
        self.assertEqual((method, url), ("POST", "http://srv/Items/i/PlaybackInfo"))
        self.assertEqual(kwargs["json"]["UserId"], "u1")
        self.assertEqual(kwargs["json"]["MediaSourceId"], "src")
        self.assertEqual(kwargs["json"]["DeviceProfile"], {"Name": "p"})

    def test_server_base_follows_redirect(self):
        self.assertEqual(server_base("https://jf.example/jellyfin/System/Info/Public"), "https://jf.example/jellyfin")
        self.assertEqual(server_base("https://jf.example/other"), "")


class LoginTest(unittest.TestCase):
    def session(self, responses):
        import requests
        s = Session(FakeSettings())
        posted = []
        s._post_anon = lambda server, path, **kw: posted.append((server, path, kw)) or responses(path)
        s._switch_to = lambda address, result, name="": posted.append(("switch", address, result["AccessToken"]))
        original = requests.get
        requests.get = lambda url, **kw: FakeResponse({"Id": "srv"}, url=url)
        self.addCleanup(setattr, requests, "get", original)
        return s, posted

    def test_login_by_name(self):
        s, posted = self.session(lambda path: {"AccessToken": "tok", "User": {"Id": "u"}})
        s.login("srv.local:8096", "ann", "pw")
        self.assertEqual(posted[0][:2], ("http://srv.local:8096", "Users/AuthenticateByName"))
        self.assertEqual(posted[0][2]["json"], {"Username": "ann", "Pw": "pw"})
        self.assertEqual(posted[1], ("switch", "http://srv.local:8096", "tok"))

    def test_wrong_password(self):
        import requests

        def reject(path):
            raise requests.HTTPError(response=FakeResponse(status=401))
        s, _ = self.session(reject)
        with self.assertRaises(LoginError):
            s.login("http://srv", "ann", "bad")


class RecordingClient:
    def __init__(self, delay=None):
        self.paths = []
        self.delay = delay

    def post(self, path, json=None, params=None):
        if self.delay:
            self.delay.wait(5)
        self.paths.append(path)


class ReporterOrderTest(unittest.TestCase):
    def test_reports_keep_order_without_blocking(self):
        gate = threading.Event()
        client = RecordingClient(gate)
        reporter = PlaybackReporter(client, "i", "s", "p")
        reporter.start(0)
        for n in range(3):
            reporter.progress(n, False)
        reporter.stop(10)
        self.assertEqual(client.paths, [])
        gate.set()
        self.assertTrue(reporter.flush(5))
        self.assertEqual(client.paths, ["Sessions/Playing"] + ["Sessions/Playing/Progress"] * 3 + ["Sessions/Playing/Stopped"])

    def test_failed_report_does_not_stop_the_rest(self):
        class Flaky(RecordingClient):
            def post(self, path, json=None, params=None):
                if path == "Sessions/Playing":
                    raise OSError("down")
                super().post(path, json, params)
        client = Flaky()
        reporter = PlaybackReporter(client, "i", "s", "p")
        reporter.start(0)
        reporter.stop(5)
        self.assertTrue(reporter.flush(5))
        self.assertEqual(client.paths, ["Sessions/Playing/Stopped"])


class MpvIpcTest(unittest.TestCase):
    def test_command_line(self):
        args = command_line("mpv", "/s", {"idle": "yes", "osc": False, "start": "5.000"})
        self.assertEqual(args, ["mpv", "--input-ipc-server=/s", "--idle=yes", "--osc=no", "--start=5.000"])

    @unittest.skipUnless(shutil.which("mpv"), "mpv not installed")
    def test_real_mpv_round_trip(self):
        exited = threading.Event()
        seen = []
        messages = []
        mpv = MpvIpc({"idle": "yes", "vo": "null", "ao": "null", "terminal": "no", "config": "no"}, on_exit=exited.set)
        mpv.bind_event("client-message", lambda m: messages.append(m.get("args")))
        mpv.start()
        try:
            for value in (True, False, True):
                got = threading.Event()
                mpv.observe("pause", lambda _n, v, got=got: (seen.append(v), got.set()))
                mpv.command("set_property", "pause", value)
                self.assertIs(mpv.command("get_property", "pause"), value)
                self.assertTrue(got.wait(5))
            with self.assertRaises(MpvError):
                mpv.command("get_property", "no-such-property")
            mpv.command("script-message", "hello", "world")
            mpv.command("quit")
            self.assertTrue(exited.wait(10))
        finally:
            mpv.terminate()
        self.assertEqual(messages, [["hello", "world"]])
        with self.assertRaises(MpvError):
            mpv.command("get_property", "pause")


if __name__ == "__main__":
    unittest.main()

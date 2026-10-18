import unittest

from aiostreamer.steam import CLEANED, clean_environment, launched_by_steam

STEAM = "/home/u/.local/share/Steam"
ENV = {
    "SteamGameId": "10261258915555573760",
    "LD_PRELOAD": STEAM + "/ubuntu12_64/gameoverlayrenderer.so",
    "LD_LIBRARY_PATH": STEAM + "/ubuntu12_32:" + STEAM + "/ubuntu12_32/steam-runtime/pinned_libs_64:/usr/lib64/ffmpeg",
    "SYSTEM_LD_LIBRARY_PATH": "",
    "STEAM_RUNTIME": STEAM + "/ubuntu12_32/steam-runtime",
    "__EGL_VENDOR_LIBRARY_DIRS": STEAM + "/ubuntu12_32/steam-runtime/usr/share/glvnd/egl_vendor.d",
    "XDG_DATA_DIRS": STEAM + "/steam-runtime/usr/share:/usr/share",
    "PATH": STEAM + "/ubuntu12_32/steam-runtime/usr/bin:/usr/bin",
    "WAYLAND_DISPLAY": "gamescope-0",
    "DISPLAY": ":1",
    "LANG": "C",
    "STEAM_URL": "steam://rungameid/1",
}
SESSION = {"LANG": "en_US.UTF-8", "WAYLAND_DISPLAY": "wayland-0", "XDG_CURRENT_DESKTOP": "KDE"}


class SteamEnvTest(unittest.TestCase):
    def test_detection(self):
        self.assertTrue(launched_by_steam(ENV))
        self.assertFalse(launched_by_steam({"PATH": "/usr/bin"}))
        self.assertFalse(launched_by_steam(dict(ENV, **{CLEANED: "1"})))

    def test_strips_steam_runtime(self):
        env = clean_environment(ENV, SESSION)
        for key in ("LD_PRELOAD", "LD_LIBRARY_PATH", "STEAM_RUNTIME", "__EGL_VENDOR_LIBRARY_DIRS"):
            self.assertNotIn(key, env)
        self.assertEqual(env["XDG_DATA_DIRS"], "/usr/share")
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["STEAM_URL"], "steam://rungameid/1")
        self.assertEqual(env[CLEANED], "1")
        self.assertFalse(launched_by_steam(env))

    def test_keeps_steam_display_and_fixes_locale(self):
        env = clean_environment(ENV, SESSION)
        self.assertEqual(env["WAYLAND_DISPLAY"], "gamescope-0")
        self.assertEqual(env["DISPLAY"], ":1")
        self.assertEqual(env["LANG"], "en_US.UTF-8")
        self.assertEqual(env["XDG_CURRENT_DESKTOP"], "KDE")
        self.assertEqual(clean_environment(dict(ENV, LANG="POSIX"), {})["LANG"], "C.UTF-8")

    def test_restores_system_paths(self):
        env = clean_environment(dict(ENV, SYSTEM_LD_LIBRARY_PATH="/opt/lib", SYSTEM_PATH="/usr/local/bin:/usr/bin"), {})
        self.assertEqual(env["LD_LIBRARY_PATH"], "/opt/lib")
        self.assertEqual(env["PATH"], "/usr/local/bin:/usr/bin")


if __name__ == "__main__":
    unittest.main()

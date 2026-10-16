# Jellyfin TV

TV-first Jellyfin/Remux frontend for Linux (PySide6 + QML), driven by remote or keyboard. Playback is handed off to an external fullscreen mpv so HDR passthrough is preserved.

## Run

```sh
sudo apt install mpv python3-venv python3-pyside6.qtquick   # or let install.sh pip-install PySide6
packaging/install.sh                                       # venv + ~/.local/bin/jellyfin-tv + menu entry
jellyfin-tv                                                # --windowed, --debug
```

From a checkout without installing: `python3 -m jellyfin_tv` (deps from `packaging/requirements.txt`).

## Features

- Home: Continue Watching, Next Up, Favorites, My Media and one row per library
- Library grid with paging and sorting (default, name, date added, release date, rating)
- Search with on-screen keyboard (or physical keyboard), movies and shows
- Movie/episode details: resume or start over, version picker, watched/favorite toggles, More like this
- Shows: seasons including Specials, episode row with thumbnails, watched and resume indicators, Play/Resume next up
- Version picker: resolution, HDR type, codec, audio, size, release info; sorted best first, choice remembered per title; versions load as the page opens and Play waits for them
- Default version capped by bitrate (40 Mbps by default) so huge remuxes are only picked on request
- Audio language "Original" plays the title's own language (series language for episodes) instead of a default dub
- Up Next card drawn by mpv at the outro or last 30 s, with countdown; the next episode continues in the same mpv
- Steam shortcuts: the app re-execs with Steam's runtime environment removed
- Accounts: Quick Connect login, several accounts/servers with switching (login page and Settings)
- Remote control from Jellyfin apps over the server websocket (play/pause/seek/stop, tracks, volume, UI navigation, messages)
- SyncPlay page (Home header): create/join/leave groups; playback follows the group clock
- Skip intro/recap button or automatic skip (server segments or chapter names)
- Trickplay previews in the uosc timeline and remote scrubbing (Left/Right preview, seek after 0.8 s or OK)
- Audio output: auto, stereo downmix or passthrough
- Gamepad (SDL2): A select, B back, Y trailer, X play/pause, Start menu, bumpers page up/down, D-pad/left stick navigate; works in the player too
- Trailer previews: the movie/show page plays its trailer in place of the backdrop (local trailer first, else RemoteTrailers, else a YouTube search for the title and year, via yt-dlp; streamed, not downloaded); Trailer button or T key plays it full screen with sound, seekable from a local cache, muted by default
- Settings: audio/subtitle language, subtitle mode, autoplay, countdown, max resolution, HDR preference, max bitrate, player controls (overlay/native), audio output, skip intros, remote control, trailer previews, mpv overrides, accounts

## Flatpak

Install from the project's Flatpak repository (updates arrive through `flatpak update` / Discover):

```sh
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak remote-add --user --if-not-exists jellyfin-tv https://gettuh.github.io/jellyfin-tv-linux/jellyfin-tv.flatpakrepo
flatpak install --user jellyfin-tv io.github.gettuh.JellyfinTV
```

The Flatpak bundles its own mpv (`gpu-next`, Vulkan, VA-API). Inside the sandbox the access token is kept in the app's private config dir (mode 0600) because the Secret Service client needs compiled crypto wheels.

## Releasing

1. Once: `packaging/flatpak/create-signing-key.sh` creates the repo signing key and stores it as the `FLATPAK_GPG_PRIVATE_KEY` secret (needs `gh`). Keep the backup it writes.
2. Once: Settings → Pages → Source: GitHub Actions.
3. `git tag v0.2.0 && git push origin v0.2.0` runs tests, builds the Flatpak, publishes the signed repo to GitHub Pages and attaches a `.flatpak` bundle to a GitHub release.

Pushes to `master` also build an unsigned test bundle (workflow artifact) without publishing. Python wheel pins live in `packaging/flatpak/python-deps.json`, regenerated with `gen_python_deps.py`.

## Tests

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s jellyfin_tv/tests -t .
```

## Keys

Arrows move, Enter selects, Esc/Back/Backspace goes back. On Home, Back asks to quit.

In mpv, Settings → Player controls picks **Overlay** (default) or **Native mpv** (mpv's own OSC and default keys; Esc/Back still returns to the app). Overlay (uosc interface, themed with the app's accent): Left/Right seek 10 s, OK pauses, Up opens the playback menu (audio, subtitles, version, chapters, stop; switching version keeps your position), Down shows the timeline, Esc/Back stops playback. Keys can be overridden in your mpv `input.conf`; if you already use uosc from `~/.config/mpv/scripts`, yours is used.

## mpv

Defaults: `vo=gpu-next gpu-api=vulkan hwdec=auto-safe target-colorspace-hint=yes fullscreen=yes`.
Override them in `~/.config/jellyfin-tv/mpv.conf` (loaded after the defaults) or the `mpv_extra` setting (one `key=value` per line).

## Files

- Settings: `~/.config/jellyfin-tv/settings.ini`
- Access token: system keyring (service `jellyfin-tv`)
- Artwork cache: `~/.cache/jellyfin-tv/images` (pruned at 600 MB)

## Layout

- `api/` session/auth, library queries, image provider, background tasks
- `player/` mpv process control, playback controller, Sessions/Playing reporting
- `models/` Qt models for home rows, grids, details, sources, settings
- `ui/` QML pages and components

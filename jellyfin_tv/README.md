# Jellyfin TV

TV-first AIOStreams client for Linux (PySide6 + QML), driven by remote or keyboard. It uses the Stremio addon protocol of your AIOStreams configuration (catalogs, meta, streams, subtitles); no Jellyfin server or Stremio app. Playback is handed off to an external fullscreen mpv so HDR passthrough is preserved.

## Run

```sh
sudo apt install mpv python3-venv python3-pyside6.qtquick   # or let install.sh pip-install PySide6
packaging/install.sh                                       # venv + ~/.local/bin/jellyfin-tv + menu entry
jellyfin-tv                                                # --windowed, --debug
```

From a checkout without installing: `python3 -m jellyfin_tv` (deps from `packaging/requirements.txt`).

## Features

- Home: Continue Watching, Next Up, My List, one row per AIOStreams catalog, and a Browse row of all catalogs
- Catalog grid with paging and genre filter (catalogs whose genre is required start at the first option)
- Search with on-screen keyboard (or physical keyboard) across catalogs that support search, movies and shows
- Movie/episode details: resume or start over, version picker, watched and My List toggles
- Shows: seasons including Specials, episode row with thumbnails, watched and resume indicators, Play/Resume next up
- Version picker: resolution, HDR, codec, audio, size, debrid service and cache status from AIOStreams' parsed stream data, in your AIOStreams sort order; choice remembered per title (by file name, then release group)
- Optional caps (Settings → Versions): maximum resolution and bitrate (estimated from size and runtime) skip versions by default
- Up Next card drawn by mpv in the last 30 s, with countdown; the next episode continues in the same mpv with the same release group (binge group)
- Subtitles from your subtitle addons, added when the file has no track in your language (two per language)
- Watch state on the device: resume points (after 60 s), watched at 90 %, Next Up from the last episode you finished
- Caching: manifest 6 h, catalogs 30 min, search 1 h, meta 24 h (6 h for airing shows), streams 15 min, subtitles 6 h; cached pages paint immediately and stale data is shown when AIOStreams is unreachable; concurrent requests for the same URL share one fetch, at most 4 requests at a time
- Accounts: several AIOStreams configurations with switching (login page and Settings)
- Skip intro/recap button or automatic skip (chapter names)
- Audio output: auto, stereo downmix or passthrough
- Steam shortcuts: the app re-execs with Steam's runtime environment removed
- Gamepad (SDL2): A select, B back, Y trailer, X play/pause, Start menu, bumpers page up/down, D-pad/left stick navigate; works in the player too
- Trailer previews: the movie/show page plays its trailer in place of the backdrop (meta trailers, else a YouTube search for the title and year, via yt-dlp; streamed, not downloaded); Trailer button or T key plays it full screen with sound, seekable from a local cache, muted by default
- Settings: audio/subtitle language, subtitle mode, autoplay, countdown, max resolution, max bitrate, player controls (overlay/native), audio output, skip intros, trailer previews, gamepad, mpv overrides, accounts, clear cache

## Signing in

Enter your instance address (e.g. `https://aiostreams.example.com`), your configuration's UUID or alias and its password. The app asks the instance for your manifest URL once and keeps only that. You can also paste the manifest URL (`.../stremio/<uuid>/<encrypted>/manifest.json`, or a `stremio://` link) into the address field.

Streams that are P2P torrents are hidden: configure a debrid or Usenet service in AIOStreams.

## Flatpak

Install from the project's Flatpak repository (updates arrive through `flatpak update` / Discover):

```sh
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak remote-add --user --if-not-exists jellyfin-tv https://gettuh.github.io/jellyfin-tv-linux/jellyfin-tv.flatpakrepo
flatpak install --user jellyfin-tv io.github.gettuh.JellyfinTV
```

The Flatpak bundles its own mpv (`gpu-next`, Vulkan, VA-API). Inside the sandbox the account list is kept in the app's private config dir (mode 0600) because the Secret Service client needs compiled crypto wheels.

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
- Accounts (manifest URLs): system keyring (service `jellyfin-tv`, key `aiostreams`), else `~/.config/jellyfin-tv/accounts.json` (0600)
- Watch state per account: `~/.config/jellyfin-tv/state/<account>.json`
- AIOStreams response cache: `~/.cache/jellyfin-tv/aio/<account>/` (entries unused for 30 days are removed)
- Artwork cache: `~/.cache/jellyfin-tv/images` (pruned at 600 MB)

## Layout

- `api/` AIOStreams client and cache, session/accounts, library queries, watch state, image provider, background tasks
- `player/` mpv process control, playback controller
- `models/` Qt models for home rows, grids, details, sources, settings
- `ui/` QML pages and components

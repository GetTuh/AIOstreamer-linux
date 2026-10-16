#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$1"
BASE_URL="${2%/}/"
KEY_ID="${3:-}"
APP_ID=io.github.gettuh.JellyfinTV
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

GPG_LINE=""
if [ -n "$KEY_ID" ]; then
    GPG_LINE="GPGKey=$(gpg --export "$KEY_ID" | base64 -w0)"
fi

cat > "$REPO_DIR/jellyfin-tv.flatpakrepo" <<INI
[Flatpak Repo]
Title=Jellyfin TV
Url=${BASE_URL}
Homepage=https://github.com/GetTuh/jellyfin-tv-linux
Comment=Remote-friendly Jellyfin client with mpv playback
Icon=${BASE_URL}icon.svg
DefaultBranch=stable
${GPG_LINE}
INI

cat > "$REPO_DIR/jellyfin-tv.flatpakref" <<INI
[Flatpak Ref]
Name=${APP_ID}
Branch=stable
Title=Jellyfin TV
Url=${BASE_URL}
SuggestRemoteName=jellyfin-tv
RuntimeRepo=https://dl.flathub.org/repo/flathub.flatpakrepo
IsRuntime=false
${GPG_LINE}
INI

cp "$ROOT/jellyfin_tv/ui/icon.svg" "$REPO_DIR/icon.svg"
touch "$REPO_DIR/.nojekyll"

cat > "$REPO_DIR/index.html" <<HTML
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jellyfin TV</title>
<style>
:root{--bg:#0f1218;--fg:#f3f5f9;--dim:#a3abba;--card:#1a1f29;--accent:#3daee9}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:48px 16px}
h1{margin:0 0 4px}p{color:var(--dim)}
pre{background:var(--card);padding:16px;border-radius:8px;overflow-x:auto;color:var(--fg)}
a{color:var(--accent)}
</style></head><body><main>
<h1>Jellyfin TV</h1>
<p>Remote-friendly Jellyfin client for Linux TV boxes, with fullscreen mpv playback.</p>
<h2>Install</h2>
<pre>flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak remote-add --user --if-not-exists jellyfin-tv ${BASE_URL}jellyfin-tv.flatpakrepo
flatpak install --user jellyfin-tv ${APP_ID}</pre>
<p>Or open <a href="jellyfin-tv.flatpakref">jellyfin-tv.flatpakref</a> in Discover.</p>
<h2>Update</h2>
<pre>flatpak update</pre>
<p>Discover and GNOME Software pick up new releases automatically once the remote is added.</p>
</main></body></html>
HTML

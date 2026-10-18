#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${AIOS_VENV:-$ROOT/.venv}"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN="$HOME/.local/bin"

if python3 -c "import PySide6.QtQuick" 2>/dev/null; then
    python3 -m venv --system-site-packages "$VENV"
else
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q "PySide6>=6.5"
fi
"$VENV/bin/pip" install -q -r "$ROOT/packaging/requirements.txt"

mkdir -p "$BIN" "$DATA/applications" "$DATA/icons/hicolor/scalable/apps"
cat > "$BIN/aiostreamer" <<SH
#!/usr/bin/env bash
cd "$ROOT"
exec "$VENV/bin/python" -m aiostreamer "\$@"
SH
chmod +x "$BIN/aiostreamer"

sed "s|@EXEC@|$BIN/aiostreamer|" "$ROOT/packaging/aiostreamer.desktop" > "$DATA/applications/aiostreamer.desktop"
cp "$ROOT/aiostreamer/ui/icon.svg" "$DATA/icons/hicolor/scalable/apps/aiostreamer.svg"
command -v update-desktop-database >/dev/null && update-desktop-database -q "$DATA/applications" || true

command -v mpv >/dev/null || echo "warning: mpv not found, install it with: sudo apt install mpv"
echo "Installed. Launch 'AIOstreamer' from the menu or run: $BIN/aiostreamer"

#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-GetTuh/jellyfin-tv-linux}"
OUT="${2:-$HOME/.local/share/jellyfin-tv-signing}"
mkdir -p "$OUT"
chmod 700 "$OUT"
export GNUPGHOME="$OUT/gnupg"
mkdir -p "$GNUPGHOME"
chmod 700 "$GNUPGHOME"

gpg --batch --passphrase '' --quick-gen-key "Jellyfin TV Flatpak <noreply@github.com>" ed25519 sign never
KEY_ID="$(gpg --list-secret-keys --with-colons | awk -F: '/^sec/ {print $5; exit}')"
gpg --armor --export-secret-keys "$KEY_ID" > "$OUT/private.asc"
gpg --armor --export "$KEY_ID" > "$OUT/public.asc"
chmod 600 "$OUT/private.asc"

gh secret set FLATPAK_GPG_PRIVATE_KEY --repo "$REPO" < "$OUT/private.asc"
echo "Key $KEY_ID stored as FLATPAK_GPG_PRIVATE_KEY in $REPO"
echo "Backup kept in $OUT (keep it safe: losing it means users must re-add the remote)"

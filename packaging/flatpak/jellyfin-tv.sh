#!/bin/sh
export PYTHONPATH=/app/share/jellyfin-tv${PYTHONPATH:+:$PYTHONPATH}
exec python3 -m jellyfin_tv "$@"

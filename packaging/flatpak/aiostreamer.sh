#!/bin/sh
export PYTHONPATH=/app/share/aiostreamer${PYTHONPATH:+:$PYTHONPATH}
exec python3 -m aiostreamer "$@"

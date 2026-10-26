#!/bin/bash
CR=$(cd "$(dirname "$0")/.." && pwd); F=$CR/work/stacks/$1.env; [ -f "$F" ] || exit 0; . "$F"
lsof -ti tcp:$HTTPPORT -sTCP:LISTEN | xargs kill 2>/dev/null; kill "$SERVER_PID" 2>/dev/null || true; pg_ctl -D "$TMP/data" stop -m fast >/dev/null 2>&1 || true; [ "${KEEP:-0}" = 1 ] || rm -rf "$TMP"; rm -f "$F"

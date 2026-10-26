#!/bin/bash
# kills leftover throwaway servers/PostgreSQL from interrupted runs (only those living in a mktemp dir)
for p in $(pgrep -f "/tmp\.[A-Za-z0-9]*/analytics-server serve"); do kill $p 2>/dev/null; done
for p in $(pgrep -f "postgres -D /var/folders"); do kill $p 2>/dev/null; done
sleep 2

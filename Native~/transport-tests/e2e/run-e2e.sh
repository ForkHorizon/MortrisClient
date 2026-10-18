#!/bin/sh
# End-to-end: the C# V7 session talks HTTP to a real MortrisServer (feat/v7-transport) backed by a throwaway PostgreSQL.
# Needs: postgres/initdb/pg_ctl/psql, go, dotnet, and the server repository (MORTRIS_SERVER_REPO). Nothing outside a temp dir is touched.
set -eu
. "$(dirname "$0")/lib.sh"
trap stack_cleanup EXIT
start_stack
cd "$HERE"
M7_E2E_URL="http://127.0.0.1:$HTTP_PORT" M7_E2E_PSQL="psql -h 127.0.0.1 -p $PGPORT -U postgres -d mortris_e2e -tA" dotnet test --filter "FullyQualifiedName~E2E" "$@"

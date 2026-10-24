#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
dotnet build research/telemetry-v7/Mortris.V7Replay.csproj --configuration Release --nologo
GOPROXY=off GOTOOLCHAIN=local go build -C research/telemetry-v7/go -o "$PWD/.local/telemetry-research/v7-replay/bin/v7-decode" .

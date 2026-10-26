#!/bin/sh
# Re-creates harness/libs from pinned upstream commits (verify with SHA256SUMS).
set -eu; D=$(cd "$(dirname "$0")" && pwd); T=$(mktemp -d)
git clone --depth 1 https://github.com/amplitude/unity-plugin "$T/amp"; git -C "$T/amp" checkout 599146150d11d818647d172a3018365253bdd263 2>/dev/null || true
git clone --depth 1 https://github.com/GameAnalytics/GA-SDK-UNITY "$T/ga"
mkdir -p "$D/libs"; cp "$T/amp/Assets/Plugins/Android/"*.aar "$T/amp/Assets/Plugins/Android/"*.jar "$D/libs/"; cp "$T/ga/Runtime/Android/gameanalytics.aar" "$D/libs/"
(cd "$D/libs" && shasum -a 256 -c SHA256SUMS)

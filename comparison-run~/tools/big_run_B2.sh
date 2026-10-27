#!/bin/bash
# continuation of chain B after the drain scenario was fixed (burst instead of the 20-event batch)
cd "$(dirname "$0")/.."
A=~/Library/Android/sdk/platform-tools/adb
python3 tools/matrix_net.py emulator-5556 18191 bigB bignet drain,flap
PORT=18191 python3 tools/matrix_profile.py emulator-5556 bigprof_B bigB profile,tls,backlog 1
$A -s emulator-5556 install -r work/cmp-new-arm64.apk >/dev/null
python3 tools/matrix_net.py emulator-5556 18191 bigB bignet long
echo CHAIN_B_DONE

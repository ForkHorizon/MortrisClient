#!/bin/bash
# usage: stress.sh N seconds -> N CPU burners (yes) for S seconds
N=$1; S=$2; PIDS=""
for i in $(seq 1 $N); do yes > /dev/null & PIDS="$PIDS $!"; done
sleep $S; kill $PIDS 2>/dev/null; wait 2>/dev/null

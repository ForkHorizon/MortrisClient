#!/bin/sh
# Builds the compression-only zstd plugin (libdaliys_zstd) from the pinned upstream source for:
#   Android arm64-v8a and armeabi-v7a (API 25, 16 KB page aligned) and the macOS Editor (universal dylib).
# Output goes to Runtime/Plugins. The source archive is downloaded once into ./cache (gitignored) and verified.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../.." && pwd)
VERSION=1.5.7; SHA256=37d7284556b20954e56e1ca85b80226768902e2edabd3b649e9e72c0c9012ee3
URL=https://codeload.github.com/facebook/zstd/tar.gz/refs/tags/v$VERSION
UNITY_EDITOR=${UNITY_EDITOR:-/Applications/Unity/Hub/Editor/6000.3.16f1}
NDK=${NDK_BIN:-$UNITY_EDITOR/PlaybackEngines/AndroidPlayer/NDK/toolchains/llvm/prebuilt/darwin-x86_64/bin}
mkdir -p "$HERE/cache"; ARCHIVE=$HERE/cache/zstd-v$VERSION.tar.gz
[ -f "$ARCHIVE" ] || curl -fsSL "$URL" -o "$ARCHIVE"
echo "$SHA256  $ARCHIVE" | shasum -a 256 -c -
SRC=$HERE/cache/zstd-$VERSION; [ -d "$SRC" ] || tar -xzf "$ARCHIVE" -C "$HERE/cache"
LIB=$SRC/lib; FILES=$(ls "$LIB"/common/*.c "$LIB"/compress/*.c)
FLAGS="-O2 -DNDEBUG -DZSTD_LEGACY_SUPPORT=0 -DZSTD_DISABLE_ASM=1 -DZSTD_MULTITHREAD=0 -fPIC -I$LIB -I$LIB/common"
build_android() { # abi compiler
  OUT=$ROOT/Runtime/Plugins/Android/$1; mkdir -p "$OUT"
  "$NDK/$2" -shared $FLAGS -Wl,-soname,libdaliys_zstd.so -Wl,--no-undefined -Wl,--gc-sections -Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384 $FILES -o "$OUT/libdaliys_zstd.so"
  "$NDK/llvm-strip" --strip-unneeded "$OUT/libdaliys_zstd.so"
}
build_android arm64-v8a aarch64-linux-android25-clang
build_android armeabi-v7a armv7a-linux-androideabi25-clang
OUT=$ROOT/Runtime/Plugins/macOS; mkdir -p "$OUT"
clang -dynamiclib -arch arm64 -arch x86_64 -mmacosx-version-min=11.0 $FLAGS -install_name @rpath/libdaliys_zstd.dylib $FILES -o "$OUT/libdaliys_zstd.dylib"
strip -x "$OUT/libdaliys_zstd.dylib"
cp "$SRC/LICENSE" "$HERE/LICENSE-zstd.txt"
for f in "$ROOT"/Runtime/Plugins/Android/*/libdaliys_zstd.so "$OUT/libdaliys_zstd.dylib"; do shasum -a 256 "$f"; done > "$HERE/SHA256SUMS"; cat "$HERE/SHA256SUMS"

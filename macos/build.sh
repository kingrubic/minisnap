#!/usr/bin/env bash
# Builds MiniSnap.app (universal when possible), ad-hoc signs it and zips it.
# Output: macos/dist/MiniSnap.app and macos/dist/MiniSnap-macOS.zip
set -euo pipefail

cd "$(dirname "$0")"

DIST="dist"
APP="$DIST/MiniSnap.app"

rm -rf "$DIST"
mkdir -p "$DIST"

echo "==> Swift toolchain"
swift --version || true

echo "==> Building (universal: arm64 + x86_64)"
if swift build -c release --arch arm64 --arch x86_64; then
    BIN_DIR="$(swift build -c release --arch arm64 --arch x86_64 --show-bin-path)"
else
    echo "Universal build failed; falling back to the native architecture." >&2
    swift build -c release
    BIN_DIR="$(swift build -c release --show-bin-path)"
fi
BIN="$BIN_DIR/MiniSnap"
if [ ! -f "$BIN" ]; then
    echo "error: built binary not found at $BIN" >&2
    exit 1
fi
lipo -info "$BIN" || true

echo "==> Assembling $APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/MiniSnap"
chmod +x "$APP/Contents/MacOS/MiniSnap"
cp Resources/Info.plist "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"

echo "==> App icon (optional)"
if swift Scripts/make_icon.swift "$DIST/AppIcon.iconset" \
    && iconutil -c icns "$DIST/AppIcon.iconset" -o "$APP/Contents/Resources/AppIcon.icns"; then
    echo "AppIcon.icns created"
else
    echo "warning: app icon could not be generated; continuing without it" >&2
fi
rm -rf "$DIST/AppIcon.iconset"

echo "==> Ad-hoc code signing"
codesign --force --deep --sign - "$APP"
codesign --verify --verbose=2 "$APP" || true

echo "==> Zipping"
ditto -c -k --keepParent "$APP" "$DIST/MiniSnap-macOS.zip"

echo "Done:"
ls -la "$DIST"

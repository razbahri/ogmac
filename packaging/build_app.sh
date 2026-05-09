#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v xcodegen >/dev/null 2>&1; then
    echo "xcodegen not found. Install with: brew install xcodegen"
    exit 1
fi

xcodegen generate

ARCHIVE_PATH="$(pwd)/build/Ogmac.xcarchive"
EXPORT_PATH="$(pwd)/dist"

mkdir -p "$EXPORT_PATH"

xcodebuild \
    -project Ogmac.xcodeproj \
    -scheme Ogmac \
    -configuration Release \
    -archivePath "$ARCHIVE_PATH" \
    archive

APP_IN_ARCHIVE="$ARCHIVE_PATH/Products/Applications/Ogmac.app"

if [ -d "$APP_IN_ARCHIVE" ]; then
    rm -rf "$EXPORT_PATH/Ogmac.app"
    cp -R "$APP_IN_ARCHIVE" "$EXPORT_PATH/Ogmac.app"
    echo "Built: $EXPORT_PATH/Ogmac.app"
else
    echo "Error: Ogmac.app not found in archive at $APP_IN_ARCHIVE" >&2
    exit 1
fi

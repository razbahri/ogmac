#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${OGMAC_VENV_DIR:-"${HOME}/.local/share/ogmac/venv"}"
PLIST_LABEL="com.ogmac.sync"
PLIST_DEST="${HOME}/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_DIR="${HOME}/Library/Logs/ogmac"
SUPPORT_DIR="${HOME}/Library/Application Support/ogmac"
CONFIG_DIR="${HOME}/.config/ogmac"

check_python() {
    if command -v python3.11 &>/dev/null; then
        PYTHON="$(command -v python3.11)"
        return
    fi
    if command -v python3 &>/dev/null; then
        local ver
        ver="$(python3 --version 2>&1 | awk '{print $2}')"
        local major minor
        major="$(echo "$ver" | cut -d. -f1)"
        minor="$(echo "$ver" | cut -d. -f2)"
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$(command -v python3)"
            return
        fi
    fi
    echo "ERROR: Python 3.11 or later is required. Install it and re-run." >&2
    exit 1
}

check_python
echo "Using Python: $PYTHON ($($PYTHON --version))"

echo "Creating venv at $VENV_DIR ..."
mkdir -p "$(dirname "$VENV_DIR")"
"$PYTHON" -m venv "$VENV_DIR"

echo "Installing ogmac from $REPO_DIR ..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$REPO_DIR"

echo "Creating required directories ..."
mkdir -p "$LOG_DIR" "$SUPPORT_DIR" "$CONFIG_DIR" "$(dirname "$PLIST_DEST")"

echo "Writing launchd plist to $PLIST_DEST ..."
OGMAC_PYTHON="$VENV_DIR/bin/python"
sed \
    -e "s|__OGMAC_PYTHON__|${OGMAC_PYTHON}|g" \
    -e "s|__OGMAC_LOG_DIR__|${LOG_DIR}|g" \
    "${REPO_DIR}/packaging/${PLIST_LABEL}.plist" \
    > "$PLIST_DEST"

echo "Registering launchd job ..."
if launchctl print "gui/$UID/$PLIST_LABEL" &>/dev/null; then
    launchctl bootout "gui/$UID" "$PLIST_DEST" || true
fi
launchctl bootstrap "gui/$UID" "$PLIST_DEST"

echo ""
echo "Install complete. Next steps:"
echo "  1. Copy your Google client_secret.json to ~/.config/ogmac/client_secret.json"
echo "  2. Edit ~/.config/ogmac/config.yaml (see README for a complete example)"
echo "  3. Run: ogmac login"
echo "  4. Run: ogmac sync   (verify first run manually)"
echo "  5. Run: ogmac status (confirm success)"
echo ""
echo "Logs: $LOG_DIR/sync.log"
echo "      $LOG_DIR/launchd.out.log"
echo "      $LOG_DIR/launchd.err.log"

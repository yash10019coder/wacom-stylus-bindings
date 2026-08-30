#!/bin/bash
# Installs the Wacom button bindings + toggle daemon for this user.
# Idempotent: safe to re-run after editing files in this repo.
set -eu

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$BIN_DIR" "$UNIT_DIR"

cp "$REPO_DIR/wacom-watch.sh" "$BIN_DIR/wacom-watch.sh"
chmod +x "$BIN_DIR/wacom-watch.sh"

cp "$REPO_DIR/wacom-button3-toggle.py" "$BIN_DIR/wacom-button3-toggle.py"
chmod +x "$BIN_DIR/wacom-button3-toggle.py"

cp "$REPO_DIR/wacom-watch.service" "$UNIT_DIR/wacom-watch.service"
cp "$REPO_DIR/wacom-button3-toggle.service" "$UNIT_DIR/wacom-button3-toggle.service"

if ! grep -q 'Wacom One by Wacom M Pen stylus" Button 3' "$HOME/.xprofile" 2>/dev/null; then
    echo "" >> "$HOME/.xprofile"
    cat "$REPO_DIR/xprofile-wacom-snippet.sh" >> "$HOME/.xprofile"
    echo "Appended snippet to ~/.xprofile"
else
    echo "~/.xprofile already references this snippet, skipping append"
fi

systemctl --user daemon-reload
systemctl --user enable --now wacom-watch.service
systemctl --user enable --now wacom-button3-toggle.service

echo "Done. Check status with:"
echo "  systemctl --user status wacom-watch.service wacom-button3-toggle.service"

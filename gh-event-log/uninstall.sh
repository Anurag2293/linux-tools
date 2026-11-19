#!/usr/bin/env bash
set -euo pipefail
systemctl --user disable --now gh-event-log.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/gh-event-log.service"
systemctl --user daemon-reload
echo "service removed; config in ~/.config/gh-event-log and data in ~/.local/share/gh-event-log were kept"
echo "delete them with: rm -r ~/.config/gh-event-log ~/.local/share/gh-event-log"

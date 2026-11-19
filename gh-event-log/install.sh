#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
unit_dir="$HOME/.config/systemd/user"
cfg="$HOME/.config/gh-event-log/config.json"

mkdir -p "$unit_dir" "$(dirname "$cfg")"
if [ "$here" = "$HOME/Code/gh-event-log" ]; then
    ln -sf "$here/gh-event-log.service" "$unit_dir/gh-event-log.service"
else
    sed "s|%h/Code/gh-event-log|$here|" "$here/gh-event-log.service" > "$unit_dir/gh-event-log.service"
fi
if [ ! -f "$cfg" ]; then
    printf '{\n  "orgs": [],\n  "allowed_ips": [],\n  "require_tailscale_tags": []\n}\n' > "$cfg"
    echo "wrote $cfg: the HTTP API stays off until you add allowed_ips (see config.example.json)"
fi

gh auth status --hostname github.com >/dev/null 2>&1 || echo "warning: gh is not authenticated; the service will back off until it is"
if [ "$(loginctl show-user "$USER" -p Linger --value)" != "yes" ]; then
    sudo loginctl enable-linger "$USER"
fi

systemctl --user daemon-reload
systemctl --user enable --now gh-event-log.service
systemctl --user --no-pager status gh-event-log.service | head -5

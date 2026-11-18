#!/usr/bin/env bash
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SRC=~/.cache/macos-look/src
UUID=mac-layout@anurag
EXT=~/.local/share/gnome-shell/extensions/$UUID
WALLPAPER=~/.local/share/backgrounds/WhiteSur-dark.jpg
FORCE=${1:-}

missing=()
for pkg in sassc gnome-shell-extensions gnome-tweaks; do
    dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q 'install ok installed' || missing+=("$pkg")
done
if ((${#missing[@]})); then
    echo "Install first: sudo apt install ${missing[*]}"
    exit 1
fi

fetch() {
    [[ -d $SRC/$1 ]] || git clone -q --depth 1 "https://github.com/vinceliuice/$1.git" "$SRC/$1"
}

mkdir -p "$SRC"
if [[ $FORCE == --force || ! -d ~/.themes/WhiteSur-Dark ]]; then
    fetch WhiteSur-gtk-theme
    (cd "$SRC/WhiteSur-gtk-theme" && { yes || true; } | TERM=xterm ./install.sh -c dark -o normal --shell -i ubuntu >/dev/null)
    rm -f ~/.local/bin/gnome-theme-switcher ~/.local/share/applications/org.gnome.GTK4ThemeSwitcher.desktop
fi
if [[ $FORCE == --force || ! -d ~/.local/share/icons/WhiteSur-dark ]]; then
    fetch WhiteSur-icon-theme
    (cd "$SRC/WhiteSur-icon-theme" && ./install.sh -t default </dev/null >/dev/null)
fi
if [[ $FORCE == --force || ! -d ~/.local/share/icons/WhiteSur-cursors ]]; then
    fetch WhiteSur-cursors
    (cd "$SRC/WhiteSur-cursors" && ./install.sh </dev/null >/dev/null)
fi
if [[ $FORCE == --force || ! -f $WALLPAPER ]]; then
    fetch WhiteSur-wallpapers
    mkdir -p "$(dirname "$WALLPAPER")"
    cp "$SRC/WhiteSur-wallpapers/4k/WhiteSur-dark.jpg" "$WALLPAPER"
fi
if [[ $FORCE == --force || ! -d ~/.local/share/fonts/Inter ]]; then
    url=$(curl -s https://api.github.com/repos/rsms/inter/releases/latest |
        python3 -c 'import json,sys; print(next(a["browser_download_url"] for a in json.load(sys.stdin)["assets"] if a["name"].endswith(".zip")))')
    tmp=$(mktemp -d)
    curl -sL -o "$tmp/inter.zip" "$url"
    unzip -q -o "$tmp/inter.zip" -d "$tmp/x"
    mkdir -p ~/.local/share/fonts/Inter
    cp "$tmp"/x/extras/ttf/Inter-*.ttf ~/.local/share/fonts/Inter/
    rm -rf "$tmp"
    fc-cache -f ~/.local/share/fonts >/dev/null
fi

if [[ ! -L $EXT ]]; then
    rm -rf "$EXT"
    mkdir -p "$(dirname "$EXT")"
    ln -s "$HERE/extension" "$EXT"
fi

mkdir -p ~/.config/gtk-3.0
ln -sfn "$HERE/gtk-3.0.css" ~/.config/gtk-3.0/gtk.css

dconf load / <"$HERE/settings.ini"

python3 - "$UUID" user-theme@gnome-shell-extensions.gcampax.github.com <<'EOF'
import sys
from gi.repository import Gio
shell = Gio.Settings.new("org.gnome.shell")
enabled = list(shell.get_strv("enabled-extensions"))
shell.set_strv("enabled-extensions", enabled + [u for u in sys.argv[1:] if u not in enabled])
EOF

apps=~/.local/share/applications
fix_wm_class() {
    [[ -f $apps/$1 ]] && sed -i "s/^StartupWMClass=$2\$/StartupWMClass=$3/" "$apps/$1"
    return 0
}
fix_wm_class slack.desktop Slack slack

vscode=~/.config/Code/User/settings.json
if [[ -f $vscode ]] && ! grep -q '"window.controlsStyle"' "$vscode"; then
    python3 - "$vscode" <<'EOF'
import sys
path = sys.argv[1]
text = open(path).read()
i = text.index("{") + 1
open(path, "w").write(text[:i] + '\n    "window.controlsStyle": "custom",' + text[i:])
EOF
fi

echo "Done. Restart GNOME Shell (Alt+F2, r, Enter) and any open GTK apps to pick up the changes."

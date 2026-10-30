#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
bin_home=${XDG_BIN_HOME:-"$HOME/.local/bin"}
app_dir="$data_home/custom-emoji-picker"
package_dir="$app_dir/emoji_picker"
desktop_dir="$data_home/applications"
launcher="$bin_home/custom-emoji-picker"
desktop_file="$desktop_dir/com.anurag.EmojiPicker.desktop"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

if ! python3 -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_version("IBus", "1.0")' >/dev/null 2>&1; then
  echo "Python GTK 3 and IBus bindings are required (python3-gi, gir1.2-gtk-3.0, gir1.2-ibus-1.0)." >&2
  exit 1
fi

if ! command -v xdotool >/dev/null 2>&1; then
  echo "xdotool is required for automatic insertion. Install it with:" >&2
  echo "  sudo apt install xdotool" >&2
  exit 1
fi

install -d "$package_dir" "$app_dir/data" "$bin_home" "$desktop_dir" "$config_home/custom-emoji-picker"
for module in __init__.py __main__.py app.py catalog.py insertion.py state.py ui.py; do
  install -m 0644 "$project_dir/emoji_picker/$module" "$package_dir/$module"
done
install -m 0644 "$project_dir/data/style.css" "$app_dir/data/style.css"
install -m 0755 "$project_dir/bin/custom-emoji-picker" "$launcher"

escaped_launcher=$(printf '%s' "$launcher" | sed 's/[&|]/\\&/g')
sed "s|@LAUNCHER@|$escaped_launcher|g" "$project_dir/data/com.anurag.EmojiPicker.desktop.in" > "$desktop_file.tmp"
install -m 0644 "$desktop_file.tmp" "$desktop_file"
rm -f "$desktop_file.tmp"

python3 "$project_dir/scripts/manage_shortcut.py" install --command "$launcher --toggle"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$desktop_dir" >/dev/null 2>&1 || true
fi

echo "Installed Custom Emoji Picker. Press Super + . to open it."


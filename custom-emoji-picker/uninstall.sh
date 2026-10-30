#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
bin_home=${XDG_BIN_HOME:-"$HOME/.local/bin"}
app_dir="$data_home/custom-emoji-picker"
launcher="$bin_home/custom-emoji-picker"

python3 "$project_dir/scripts/manage_shortcut.py" uninstall --command "$launcher --toggle"

rm -f "$launcher"
rm -f "$data_home/applications/com.anurag.EmojiPicker.desktop"
for module in __init__.py __main__.py app.py catalog.py insertion.py state.py ui.py; do
  rm -f "$app_dir/emoji_picker/$module"
done
rm -f "$app_dir/data/style.css"
rmdir "$app_dir/emoji_picker" "$app_dir/data" "$app_dir" 2>/dev/null || true

if [ "${1:-}" = "--purge" ]; then
  rm -f "$config_home/custom-emoji-picker/state.json"
  rmdir "$config_home/custom-emoji-picker" 2>/dev/null || true
  echo "Removed application, shortcut, favorites, and recents."
else
  echo "Removed application and shortcut. Favorites and recents were preserved."
fi


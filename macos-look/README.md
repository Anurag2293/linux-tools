# macos-look

Makes the GNOME 3.36 desktop (Ubuntu 20.04, X11) look like macOS: WhiteSur-Dark theme, icons
and cursors, the Inter font, window buttons on the left, Ubuntu Dock at the bottom, and a small
Shell extension that moves the clock to the right and shows notification banners top-right.

## What it changes

| Area | Change | Where |
|---|---|---|
| App and shell theme | WhiteSur-Dark (GTK 2/3 and Shell), Ubuntu logo on Activities | `~/.themes/WhiteSur-Dark*`, User Themes extension |
| Icons, cursor | WhiteSur-dark, WhiteSur-cursors | `~/.local/share/icons/` |
| Font | Inter 10 for UI and documents, Inter Semi-Bold 10 for title bars | `~/.local/share/fonts/Inter/` |
| Window buttons | Left side: close, minimize, maximize | `settings.ini` |
| Wallpaper | WhiteSur-dark, desktop and lock screen | `~/.local/share/backgrounds/WhiteSur-dark.jpg` |
| Dock | Ubuntu Dock at the bottom, 44px icons, auto-hide, gray running dots, click shows window previews | `settings.ini` |
| Clock | Weekday and 12-hour time, at the right end of the top bar | `settings.ini`, `extension/` |
| Notifications | Banners in the top-right corner | `extension/` |
| Launchers | `StartupWMClass` fixed for Slack, Chrome Beta and one Chrome app so the dock matches their windows | `~/.local/share/applications/` |
| VS Code | `"window.controlsStyle": "custom"` keeps its buttons on the right | `~/.config/Code/User/settings.json` |
| T3 Code | Traffic lights in T3's own top bar | `t3code/` (see below) |

`settings.ini` is a `dconf` file: every gsettings value this tool sets is in it.

## Install

```sh
sudo apt install sassc gnome-shell-extensions gnome-tweaks
./install.sh            # skips themes, font and wallpaper that are already installed
./install.sh --force    # reinstalls them from upstream
```

Then restart GNOME Shell once (Alt+F2, `r`, Enter). The extension is symlinked to
`~/.local/share/gnome-shell/extensions/mac-layout@anurag`, so editing `extension/` here edits the
live copy (a Shell restart loads the change).

Chrome needs one manual step: Settings, Appearance, Theme, GTK. Without it, Chrome app windows
draw their own buttons instead of the WhiteSur ones.

## T3 Code

The traffic-light patch lives as a commit on the local `fork/desktop` branch in
`~/Code/t3code`, which [t3code-fork](../t3code-fork/) rebuilds after each nightly.
`t3code/*.patch` is a copy of that commit, for when the checkout is lost:
`git am` it onto `fork/desktop`, then `t3-fork run --force`.

## Undo

The first install on rr-gazelle (2026-11-17) saved the previous state in
`~/.local/share/macos-look/`:

1. Settings: `dconf load / < ~/.local/share/macos-look/dconf-before-20261117-1907.ini`.
2. Launchers: copy `~/.local/share/macos-look/desktop-before/*` back to `~/.local/share/applications/`.
3. VS Code: delete the `window.controlsStyle` line, or copy `vscode-settings-before.json` back.
4. Extension: `rm ~/.local/share/gnome-shell/extensions/mac-layout@anurag`.
5. Restart GNOME Shell.

The themes, icons, font and wallpaper can stay installed; nothing uses them once the settings are
restored. To drop the T3 patch, revert its commit on `fork/desktop`, then `t3-fork run --force`.

## Limits

- Electron apps that draw their own window buttons (Grok Bot) keep them.
- Ubuntu Dock on 3.36 shows window previews on click, not on hover.
- GNOME 3.36 has no global menu bar, so the top bar shows only the app name.

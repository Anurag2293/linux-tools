# fileview

Tailnet file viewer for agent links. The URL path is the filesystem path, for example
`https://my-machine.my-tailnet.ts.net/home/me/Code/fileview/README.md`, and the page
behaves differently depending on who opens it:

- **the machine itself** (`local_clients`): text files and folders jump into local VS Code; office files and PDFs open in
  the desktop app. Add `?view` to stay in the browser.
- **phone or web**: a browser IDE with file tree, tabs, search and outline; Markdown, code,
  CSV, Excel, Word, slides, images and video render in the page.
- **clients listed under `editors`**: the same page, plus "Open in <editor>" buttons.

See the docstring at the top of `fileview.py` for the query flags.

## Layout

| Path | Purpose |
| --- | --- |
| `fileview.py` | The server (stdlib `http.server`, listens on `127.0.0.1:8765`) |
| `static/` | UI assets served at `/_fv/static/` (`app.js`, `app.css`, Geist fonts) |
| `fileview.service` | systemd user unit |
| `config.example.json` | Template for `~/.config/fileview/config.json` |

## Configure

Machine-specific settings live outside the repo in `~/.config/fileview/config.json`
(override the path with `FILEVIEW_CONFIG`). Start from the example:

```bash
mkdir -p ~/.config/fileview
cp config.example.json ~/.config/fileview/config.json
```

| Key | Meaning | Default |
| --- | --- | --- |
| `public_url` | Base URL used by "Copy link" | `http://127.0.0.1:8765` |
| `machine` | Name shown in the header and status bar | hostname |
| `local_clients` | Client IPs that count as this machine (`127.0.0.1` always does) | `[]` |
| `editors` | Client IP to `[label, URL template]` pairs; templates take `{path}`, `{line}`, `{end}` | `{}` |

## Install

Dependencies: `python3-markdown`, `python3-pygments`, `mammoth`, `openpyxl`, plus
`libreoffice` and `poppler-utils` for slide and page images.

```bash
ln -sf ~/Code/fileview/fileview.service ~/.config/systemd/user/fileview.service
systemctl --user daemon-reload
systemctl --user enable --now fileview
tailscale serve --bg --https=443 http://127.0.0.1:8765
```

After editing, run `systemctl --user restart fileview`. Asset URLs carry the file mtime, so
browsers pick up CSS and JS changes on reload.

Caches (slide PNGs, extracted media) live in `~/.cache/fileview`.

## Android app

`android/` is a native Kotlin (Jetpack Compose) client for Android phones on the tailnet. It opens
fileview links instead of the browser and renders folders, code, Markdown, sheets, slides, PDFs,
images and video natively, using the `?api` JSON endpoint. Set the server URL in
`android/gradle.properties` (`fileviewHome`), then build with JDK 17 and the Android SDK:

```bash
cd android && echo "sdk.dir=$HOME/Android/Sdk" > local.properties
JAVA_HOME=~/.local/jdk17 ./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

On Android 12+, allow the app to open the fileview host under App info > Open by default.

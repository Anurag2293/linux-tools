# ferry

Grab screenshots from the Pixel 7 Pro on rr-gazelle over adb, with no Mac in the loop. A
Linux cut of the Mac's Ferry: the same `shot` and `last` commands, but no Syncthing; `last`
pulls straight from the phone.

```
ferry shot           screenshot the phone now (prints path, copies image)
ferry last [N]       pull the newest N phone screenshots (copies the newest)
ferry status         adb devices, paths and the watcher
ferry watch          pull every new phone screenshot as it appears
ferry tcp            re-enable adb over Tailscale (port 5555, resets on phone reboot)
ferry pair HOST:PORT CODE   pair with Wireless debugging
ferry adb ...        run adb against the phone
```

Images land in `~/Pictures/ferry/`.

## Watcher

`ferry-watch.service` (systemd user unit) runs `ferry watch`: it lists the phone's Screenshots
folder every 3 s, and each new screenshot is pulled and handed to `snap-corner --show`: a
draggable card at the bottom right of the monitor under the pointer, also copied to the
clipboard. Without snap-corner it falls back to the clipboard and a desktop notification. Screenshots that existed when it started are skipped. While the phone is
unreachable it retries every 15 s.

```
journalctl --user -u ferry-watch -f
systemctl --user restart ferry-watch     # after editing ferry
```

## How it reaches the phone

- **Office Wi-Fi:** the phone is paired with Wireless debugging, and adb finds it by mDNS
  (`adb-<serial>._adb-tls-connect._tcp`). Preferred when present.
- **Tailscale:** `adb connect 100.71.48.103:5555`, tried when no device is listed. Needs
  `ferry tcp` once after every phone reboot, while one of the routes above works.
- Emulators (`emulator-*`) are ignored.

## Clipboard

There is no `xclip` and no clipboard manager here, so a detached GTK process owns the image
until something else is copied, then exits. It uses `DISPLAY=:0` when run without one.

## Dependencies and install

adb from the Android SDK (`~/Android/Sdk/platform-tools/adb`, or any `adb` on the PATH) and
the system `python3-gi`.

```
ln -sf ~/Code/ferry/ferry ~/.local/bin/ferry
ln -sf ~/Code/ferry/ferry-watch.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now ferry-watch
```

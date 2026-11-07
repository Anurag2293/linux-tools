# lens

Translate everything on screen in place, like Google Translate's screen translation on Android.
**Double-tap right Alt**: the monitor under the pointer is captured, read with PP-OCRv5 on this
machine, translated with Google Translate, and the English is painted over the Japanese in a
full-screen overlay, matching each block's background and text color.

A sibling of `lens` in [mac-tools](https://github.com/Anurag2293/mac-tools), which does the same
on macOS with Apple's Vision OCR.

- OCR: [RapidOCR](https://github.com/RapidAI/RapidOCR) running PaddleOCR's PP-OCRv5 mobile
  models (Japanese, Chinese and English in one model) on OpenVINO, which is about 1.7x faster
  than onnxruntime on the i7-10750H. A 1080p screen takes 1 to 2 s. Tesseract's Japanese is
  much weaker on UI text, and the PP-OCRv5 server model takes over a minute on the CPU.
- Translation: the endpoint Chrome's built-in page translation uses
  (`translate-pa.googleapis.com/v1/translateHtml` with Chrome's public key), one request for
  the whole screen, about 0.3 s. Only the recognized text is sent, never the screenshot.
  Translations are cached, so after scrolling, text you already saw comes back instantly.
- Lines that are already English are left alone.

Overlay keys: **Esc**, a click, a scroll or the double-tap again dismisses it. Hold **Shift** to
see the original. **Ctrl+C** copies the whole translation.

## Install

```sh
./install.py               # venv in ~/.local/share/lens (with system gi and cairo),
                           # ~/.local/bin/lens, systemd user service lens.service
./install.py --uninstall [--purge]
```

No sudo. The service is part of `graphical-session.target` and takes `DISPLAY` from the
user manager's environment.

## Usage

```sh
lens                       # show or dismiss the overlay (same as the double-tap)
lens file shot.png --out translated.png   # test on an image without the screen
lens status | logs
```

Settings are environment variables read at install time:

```sh
LENS_HOTKEY=double:rctrl LENS_FROM=zh LENS_TO=en ./install.py
```

`LENS_HOTKEY` is `double:` plus `ralt` (default), `lalt`, `rctrl`, `lctrl`, `rshift`,
`lshift`, `rsuper` or `lsuper`. A tap counts only if the key is released within 0.35 s with no
other key or click in between, and the second tap must follow within 0.35 s, so shortcuts using
the key never trigger it. Avoid `lsuper`: GNOME opens the overview on each tap.

## How it works

`lens.py` is one file: a GTK 3 daemon plus the CLI. It re-executes itself under the venv's
Python, so the `~/.local/bin/lens` symlink works from any shell.

1. The trigger is watched through the X RECORD extension (python-xlib), which sees key events
   without grabbing anything or needing root.
2. GDK copies the monitor under the pointer from the root window, and the overlay (an
   override-redirect window with an RGBA visual and a seat grab, like snap-corner's selection)
   appears at once with a "Reading…" pill.
3. PP-OCRv5 returns text lines with boxes in a worker thread.
4. Lines are grouped into paragraphs: stacked, left-aligned lines of similar height form a
   block, which splits where a line does not reach the block's right edge (it did not wrap),
   ends a sentence, or the next line starts with a bullet. Wrapped Japanese lines are joined
   without spaces so sentences translate whole. Paragraphs without kana or kanji are skipped.
5. Google translates all paragraphs in one request.
6. Each block is painted with the median color of a ring around it, and the text color is the
   mean of the pixels inside that differ most from the background. Pango picks the largest
   font that fits; single-line labels may widen up to the next text on the same row.

Log: `journalctl --user -u lens`.

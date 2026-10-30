#!/usr/bin/env python3
"""Drive an already-open gedit window through the full picker flow on X11."""

import argparse
import os
import subprocess
import time
from pathlib import Path


LAUNCHER = "/home/anurag/.local/bin/custom-emoji-picker"


def run(*arguments: str) -> str:
    result = subprocess.run(
        list(arguments),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
    )
    return result.stdout.strip()


def active_window_name() -> str:
    return run("xdotool", "getactivewindow", "getwindowname")


def ensure_picker_running() -> None:
    result = subprocess.run(
        ("pgrep", "-f", "python3 -m emoji_picker"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0:
        run(LAUNCHER, "--hide")
        return
    subprocess.Popen(
        (LAUNCHER, "--hide"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=os.environ.copy(),
    )
    time.sleep(0.8)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("window_id")
    parser.add_argument("target_file", type=Path)
    args = parser.parse_args()

    ensure_picker_running()
    time.sleep(0.2)
    run("xdotool", "windowactivate", "--sync", args.window_id)
    run("xdotool", "mousemove", "--window", args.window_id, "180", "180", "click", "1")
    run("xdotool", "key", "--clearmodifiers", "ctrl+a", "BackSpace")
    run("xdotool", "type", "--clearmodifiers", "PRECHECK")
    run("xdotool", "key", "--clearmodifiers", "ctrl+s")
    time.sleep(0.3)
    if args.target_file.read_text(encoding="utf-8").strip() != "PRECHECK":
        raise RuntimeError("the temporary editor did not accept baseline keyboard input")
    run("xdotool", "key", "--clearmodifiers", "ctrl+a", "BackSpace")
    run("xdotool", "key", "--clearmodifiers", "ctrl+s")
    time.sleep(0.2)
    run("xdotool", "key", "--clearmodifiers", "super+period")
    time.sleep(0.7)

    picker_window = active_window_name()
    if picker_window != "Emoji Picker":
        raise RuntimeError("picker did not receive focus; active window is {!r}".format(picker_window))

    run("xdotool", "type", "--clearmodifiers", "--delay", "15", "grinning face")
    time.sleep(0.25)
    run("xdotool", "key", "--clearmodifiers", "Down", "Return")
    time.sleep(0.8)

    restored_window = active_window_name()
    if "custom-emoji-picker-target.txt" not in restored_window:
        raise RuntimeError("target focus was not restored; active window is {!r}".format(restored_window))
    run("xdotool", "key", "--clearmodifiers", "ctrl+s")
    time.sleep(0.4)
    value = args.target_file.read_text(encoding="utf-8").strip()
    if value != "😀":
        raise RuntimeError("expected grinning face in target file, found {!r}".format(value))
    print("End-to-end X11 insertion passed: {} -> {!r}".format(picker_window, value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

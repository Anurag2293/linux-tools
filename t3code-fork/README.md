# t3code-fork

Keeps small UI patches in the T3 Code desktop app on rr-gazelle. The stock nightly AppImage
keeps updating itself; after each update this rebuilds the same version with the patches and
swaps it in. The T3 server is never touched.

## Why it works this way

- A timer, not a path unit: the updater unlinks the file and then moves the new one in, and a
  path unit can miss the second event while its service is still running. Each timer run only
  `stat`s the file unless it changed.
- The web UI is bundled in the desktop app, so a UI patch needs only a desktop rebuild. The
  server (`t3code.service`) stays stock and updates through "Update server" as usual.
- The fork build carries the **exact** stock version string. A different version makes the UI
  flag the stock server as outdated, and electron-updater compares versions with `semver.eq`, so
  a same-version fork is never "updated" back to stock.
- The fork AppImage keeps the GitHub update feed (`app-update.yml`), so "Check for updates"
  works. When the next nightly lands, the app installs stock, and the next timer run sees the
  file change and rebuilds the fork on that version.
- Each run also unmounts dead `/tmp/.mount_T3-*` folders. When the app relaunches itself after
  an update, the new process inherits PATH entries for earlier AppImage mounts; once one of those
  dies, looking up `xdg-open` fails with "Transport endpoint is not connected" and links stop
  opening in the browser.
- Public cloud config (Clerk key, relay URL) comes from the repo's `.env.example`, the same
  values the stock build uses.

## Pieces

| What | Where |
| --- | --- |
| Patches | branch `fork/desktop` in `~/Code/t3code`: a nightly tag plus the patch commits. Not pushed. |
| Build worktree | `~/Code/t3code/.worktrees/fork-build` (detached, reset every run) |
| Script | `t3-fork`, symlinked to `~/.local/bin/t3-fork` |
| State | `~/.t3/fork/`: logs, `placed.*` (the last file this script put in place), the last stock AppImage, `last-result` |
| Units | `systemd/t3-fork.timer` (every 10 minutes) starts `t3-fork.service` |

```sh
t3-fork status        # installed version, fork or stock
t3-fork run [--force] # rebuild if the installed AppImage is stock
t3-fork restart       # quit and relaunch the desktop app (10 s warning)
t3-fork rollback      # put the last stock AppImage back
journalctl --user -u t3-fork.service   # or ~/.t3/fork/logs/
```

## Install the units

```sh
ln -sfn ~/Code/t3code-fork/systemd/t3-fork.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now t3-fork.timer
```

## Each nightly

1. T3 Code offers an update; install it as usual. The app relaunches on stock.
2. Within 10 minutes the timer starts a build (a few minutes, niced, capped at 10 GB of RAM).
3. When the fork is in place, a notification says "T3 Code restarts in 10 seconds", and the
   script quits and relaunches the desktop app. Only the desktop client restarts; the T3 server
   and its agent threads keep running. `t3-fork restart` does the same by hand.

If the patch no longer applies to a new nightly, or the build or its checks fail, the run stops
and leaves stock in place. It then opens a T3 thread in the `~/Code` project ("Fix T3 fork build
on <tag>", `t3 thread start`) that rebases or fixes `fork/desktop` and runs
`t3-fork run --force`, and notifies. The thread commits its fixes: patch changes on
`fork/desktop` (never pushed), and changes to `t3code-fork/` in `~/Code`, pushed to `origin`.
It opens one thread per nightly tag and records it in `~/.t3/fork/fix-thread.<tag>`; later timer runs that fail on the same tag only log. Delete that
file to have the next failing run open a new thread. `T3_FORK_FIX_PROJECT`,
`T3_FORK_FIX_PROVIDER` and `T3_FORK_FIX_MODEL` choose where it runs and on which model.

To fix it by hand instead: rebase `fork/desktop` onto the new tag, then `t3-fork run --force`.

The `~/Code` project's `t3.json` offers scripts for status, rebuild, rollback and restart. Import
them once from "From t3.json" in the T3 scripts menu.

## Adding a patch

Commit it on `fork/desktop` (on top of the current nightly tag). The repo's pre-commit hook needs
git 2.32, and this machine has 2.25: run `vp fmt` and `vp lint` on the files yourself, then
commit with `--no-verify`. Run `t3-fork run --force` to build it now.

## Build prerequisites

Node 26.12.1 under `~/.nvm`, `corepack` on PATH, `cargo`, `g++-10` (Electron's headers need
C++20; the default g++ 9 can't), `libsecret-1-dev`, ImageMagick.

There is no typecheck step: upstream's checker (`effect-tsgo tsrs`) is a binary that needs
glibc 2.34, and Ubuntu 20.04 has 2.31. The run instead checks that the patch is in the built
bundle.

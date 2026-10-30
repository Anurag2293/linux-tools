# linux-tools

Small tools I use every day on Ubuntu 20.04 (GNOME on X11). Each folder is a
self-contained tool with its own README and install steps.

| Tool | What it does |
| --- | --- |
| [custom-emoji-picker](custom-emoji-picker/) | Keyboard-first GTK emoji picker |
| [fileview](fileview/) | Tailnet file viewer behind agent links (systemd user service) |
| [snap-corner](snap-corner/) | Native GTK screenshot tool |

## Conventions

- One folder per tool, named after the tool. Nothing tool-specific at the root.
- Each tool has a `README.md` covering what it does, dependencies, and how to install it.
- Installed copies point back here with symlinks (`~/.local/bin`, `~/.config/systemd/user`,
  and so on), so editing the repo is editing the live tool.
- Commit messages start with the tool name: `fileview: play videos embedded in pptx`.
- Upstream projects checked out alongside (for example `t3code/`) are gitignored.

## License

[MIT](LICENSE)

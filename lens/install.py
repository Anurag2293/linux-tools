#!/usr/bin/python3
"""Install or remove lens for the current user; no sudo needed.

  ./install.py              venv + OCR models, ~/.local/bin/lens, systemd user service
  ./install.py --uninstall  stop and remove the service and launcher (add --purge for the venv)

LENS_FROM, LENS_TO and LENS_HOTKEY set at install time are written into the service.
"""
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
SOURCE = Path(__file__).resolve().parent
VENV = HOME / ".local/share/lens/venv"
LAUNCHER = HOME / ".local/bin/lens"
SERVICE = HOME / ".config/systemd/user/lens.service"
PACKAGES = ["rapidocr", "onnxruntime", "openvino<2025", "python-xlib"]  # openvino 2025 drops Python 3.8


def run(*cmd):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def install():
    if not (VENV / "bin/python").exists():
        run(sys.executable, "-m", "venv", "--system-site-packages", VENV)  # system gi and cairo
        run(VENV / "bin/pip", "install", "-q", "--upgrade", "pip")
    run(VENV / "bin/pip", "install", "-q", *PACKAGES)
    print("warming up the OCR models (downloads them on first run)")
    run(VENV / "bin/python", SOURCE / "lens.py", "warmup")

    LAUNCHER.parent.mkdir(parents=True, exist_ok=True)
    if LAUNCHER.is_symlink() or LAUNCHER.exists():
        LAUNCHER.unlink()
    LAUNCHER.symlink_to(SOURCE / "lens.py")

    env = "".join(f"Environment={k}={os.environ[k]}\n" for k in ("LENS_FROM", "LENS_TO", "LENS_HOTKEY")
                  if os.environ.get(k))
    SERVICE.parent.mkdir(parents=True, exist_ok=True)
    SERVICE.write_text(f"""[Unit]
Description=lens: translate everything on screen in place
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart={VENV}/bin/python -u {SOURCE / 'lens.py'} daemon
{env}Restart=always
RestartSec=3

[Install]
WantedBy=graphical-session.target
""")
    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", "lens")
    run("systemctl", "--user", "restart", "lens")
    print(f"installed: {LAUNCHER}, {SERVICE}")


def uninstall(purge):
    subprocess.run(["systemctl", "--user", "disable", "--now", "lens"], check=False)
    for path in (SERVICE, LAUNCHER):
        if path.is_symlink() or path.exists():
            path.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    if purge:
        run("rm", "-rf", VENV.parent)
    print("removed lens" + (" and its venv" if purge else ""))


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        uninstall("--purge" in sys.argv)
    else:
        install()

from __future__ import annotations

import json
import os

DEFAULT_PATH = os.path.expanduser("~/.config/gh-event-log/config.json")

DEFAULTS = {
    "orgs": [],
    "poll_interval_s": 120,
    "backfill_days": 14,
    "track_open_days": 60,
    "full_refresh_every": 10,
    "detail_batch_size": 8,
    "db_path": "~/.local/share/gh-event-log/events.db",
    "bind_host": "tailscale",
    "bind_port": 8787,
    "allowed_ips": [],
    "require_tailscale_tags": [],
    "body_max_chars": 4000,
    "graphql_min_remaining": 500,
    "rest_min_remaining": 200,
    "max_backoff_s": 1800,
    "gh_bin": "gh",
    "tailscale_bin": "tailscale",
}


def load(path: str | None = None) -> dict:
    path = path or os.environ.get("GH_EVENT_LOG_CONFIG") or DEFAULT_PATH
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path) as f:
            user = json.load(f)
        unknown = set(user) - set(DEFAULTS)
        if unknown:
            raise ValueError(f"unknown config keys in {path}: {sorted(unknown)}")
        cfg.update(user)
    if cfg["bind_host"] in ("0.0.0.0", "::", ""):
        raise ValueError("bind_host must be the tailnet IP or 'tailscale', never a wildcard")
    cfg["db_path"] = os.path.expanduser(cfg["db_path"])
    cfg["config_path"] = path
    return cfg

"""Persistent favorites and recent emoji state."""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


STATE_VERSION = 1
MAX_RECENTS = 30


def default_state_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home) if config_home else Path.home() / ".config"
    return root / "custom-emoji-picker" / "state.json"


class PickerState:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_state_path()
        self.favorites: List[str] = []
        self.recents: List[str] = []
        self.load()

    @staticmethod
    def _clean_values(value: Any, limit: Optional[int] = None) -> List[str]:
        if not isinstance(value, list):
            return []
        cleaned: List[str] = []
        for item in value:
            if isinstance(item, str) and item and item not in cleaned:
                cleaned.append(item)
            if limit is not None and len(cleaned) >= limit:
                break
        return cleaned

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("state root must be an object")
            self.favorites = self._clean_values(payload.get("favorites"))
            self.recents = self._clean_values(payload.get("recents"), MAX_RECENTS)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            backup = self.path.with_name(
                "state.corrupt-{}.json".format(time.time_ns())
            )
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self.favorites = []
            self.recents = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(".state.{}.tmp".format(os.getpid()))
        payload: Dict[str, Any] = {
            "version": STATE_VERSION,
            "favorites": self.favorites,
            "recents": self.recents,
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(str(temporary), 0o600)
        os.replace(str(temporary), str(self.path))

    def is_favorite(self, value: str) -> bool:
        return value in self.favorites

    def toggle_favorite(self, value: str) -> bool:
        if value in self.favorites:
            self.favorites.remove(value)
            added = False
        else:
            self.favorites.insert(0, value)
            added = True
        self.save()
        return added

    def add_recent(self, value: str) -> None:
        if value in self.recents:
            self.recents.remove(value)
        self.recents.insert(0, value)
        del self.recents[MAX_RECENTS:]
        self.save()


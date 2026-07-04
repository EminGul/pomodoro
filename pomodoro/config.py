from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pomodoro.playlist import Song

CONFIG_DIR = Path.home() / ".config" / "pomodoro"
CONFIG_FILE = CONFIG_DIR / "config.json"

PRESETS: dict[str, dict[str, int]] = {
    "classic": {"work": 25 * 60, "short_break": 5 * 60,  "long_break": 15 * 60},
    "long":    {"work": 50 * 60, "short_break": 10 * 60, "long_break": 30 * 60},
    "short":   {"work": 15 * 60, "short_break": 3 * 60,  "long_break": 10 * 60},
    "test":    {"work": 10,      "short_break": 5,       "long_break": 10},
}


@dataclass
class Config:
    work_secs: int = 25 * 60
    short_break_secs: int = 5 * 60
    long_break_secs: int = 15 * 60
    sessions_before_long_break: int = 4
    songs: list[Song | None] = field(default_factory=list)
    shuffle: bool = False
    loop: bool = False
    volume: int = 100

    @property
    def song_urls(self) -> list[str]:
        """URLs of the filled playlist slots, in slot order."""
        return [s.url for s in self.songs if s is not None]

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> Config:
        if not CONFIG_FILE.exists():
            return cls()
        try:
            data = json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "songs" in known:
            known["songs"] = [_load_song(s) for s in known["songs"]]
        return cls(**known)

    def apply_preset(self, preset: str) -> None:
        if preset not in PRESETS:
            raise ValueError(
                f"Unknown preset '{preset}'. Choose from: {', '.join(PRESETS)}"
            )
        p = PRESETS[preset]
        self.work_secs = p["work"]
        self.short_break_secs = p["short_break"]
        self.long_break_secs = p["long_break"]


def _load_song(entry: object) -> Song | None:
    """Reconstruct a slot entry, tolerating the pre-playlist plain-URL format."""
    if entry is None:
        return None
    if isinstance(entry, str):
        return Song(url=entry, name=entry)
    return Song(**entry)

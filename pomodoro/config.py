from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pomodoro.playlist import Song, filled

CONFIG_DIR = Path.home() / ".config" / "pomodoro"
CONFIG_FILE = CONFIG_DIR / "config.json"

PRESETS: dict[str, dict[str, int]] = {
    "classic": {"work": 25 * 60, "short_break": 5 * 60,  "long_break": 15 * 60},
    "long":    {"work": 50 * 60, "short_break": 10 * 60, "long_break": 30 * 60},
    "short":   {"work": 15 * 60, "short_break": 3 * 60,  "long_break": 10 * 60},
    "test":    {"work": 10,      "short_break": 5,       "long_break": 10},
}


DEFAULT_PLAYLIST = "default"


@dataclass
class Config:
    work_secs: int = 25 * 60
    short_break_secs: int = 5 * 60
    long_break_secs: int = 15 * 60
    sessions_before_long_break: int = 4
    playlists: dict[str, list[Song | None]] = field(default_factory=lambda: {DEFAULT_PLAYLIST: []})
    active_playlist: str = DEFAULT_PLAYLIST
    shuffle: bool = False
    loop: bool = False
    volume: int = 100
    watch: bool = False

    @property
    def songs(self) -> list[Song | None]:
        """Songs in the active playlist.

        `active_playlist` may legitimately point at a name not yet in
        `playlists` - the playlist editor's carousel lets you preview a
        not-yet-created slot. `setdefault` lazily materializes it the first
        time something is actually added, rather than the editor having to
        create empty playlists just by looking at them.
        """
        return self.playlists.setdefault(self.active_playlist, [])

    @songs.setter
    def songs(self, value: list[Song | None]) -> None:
        self.playlists[self.active_playlist] = value

    @property
    def song_urls(self) -> list[str]:
        """URLs of the active playlist's filled slots, in slot order."""
        return [s.url for s in filled(self.songs)]

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
        if "playlists" in known:
            known["playlists"] = {
                name: [_load_song(s) for s in slots]
                for name, slots in known["playlists"].items()
            }
        elif "songs" in data:
            # Migrate pre-multi-playlist configs, which stored a single flat list.
            known["playlists"] = {DEFAULT_PLAYLIST: [_load_song(s) for s in data["songs"]]}
        if not known.get("playlists"):
            known["playlists"] = {DEFAULT_PLAYLIST: []}
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

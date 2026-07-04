from __future__ import annotations

import json
import time
from pathlib import Path

from pomodoro.config import CONFIG_DIR
from pomodoro.timer import TimerState

STATE_FILE = CONFIG_DIR / "state.json"
PID_FILE = CONFIG_DIR / "daemon.pid"
SOCK_FILE = CONFIG_DIR / "daemon.sock"


def write_state(
    state: TimerState,
    music_playing: bool,
    mpv_available: bool = True,
    paused: bool = False,
    song_title: str | None = None,
) -> None:
    data = {
        "session_type": state.session_type.value,
        "seconds_remaining": state.seconds_remaining,
        "work_session_count": state.work_session_count,
        "total_work_sessions": state.total_work_sessions,
        "sessions_before_long_break": state.sessions_before_long_break,
        "music_playing": music_playing,
        "mpv_available": mpv_available,
        "paused": paused,
        "song_title": song_title,
        "updated_at": time.time(),
    }
    STATE_FILE.write_text(json.dumps(data))


def read_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def write_pid(pid: int) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def clear_state() -> None:
    for f in (STATE_FILE, PID_FILE, SOCK_FILE):
        f.unlink(missing_ok=True)

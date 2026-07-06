from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SessionType(Enum):
    WORK = "work"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"


@dataclass
class TimerState:
    session_type: SessionType
    seconds_remaining: int
    work_session_count: int
    total_work_sessions: int
    sessions_before_long_break: int
    session_total_seconds: int = 0

    def tick(self) -> bool:
        """Decrement by one second. Returns True when the session has ended."""
        self.seconds_remaining -= 1
        return self.seconds_remaining <= 0

    def advance(self, work_secs: int, short_break_secs: int, long_break_secs: int) -> None:
        """Transition to the next session."""
        if self.session_type == SessionType.WORK:
            self.total_work_sessions += 1
            self.work_session_count += 1
            if self.work_session_count >= self.sessions_before_long_break:
                self.session_type = SessionType.LONG_BREAK
                self.seconds_remaining = long_break_secs
                self.session_total_seconds = long_break_secs
                self.work_session_count = 0
            else:
                self.session_type = SessionType.SHORT_BREAK
                self.seconds_remaining = short_break_secs
                self.session_total_seconds = short_break_secs
        else:
            self.session_type = SessionType.WORK
            self.seconds_remaining = work_secs
            self.session_total_seconds = work_secs

    @classmethod
    def initial(cls, work_secs: int, sessions_before_long_break: int) -> TimerState:
        return cls(
            session_type=SessionType.WORK,
            seconds_remaining=work_secs,
            work_session_count=0,
            total_work_sessions=0,
            sessions_before_long_break=sessions_before_long_break,
            session_total_seconds=work_secs,
        )

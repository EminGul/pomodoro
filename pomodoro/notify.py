from __future__ import annotations

import glob
import shutil
import subprocess
from typing import Protocol


# Any class with a `send` method matching this signature is a valid Notifier.
class Notifier(Protocol):
    # `available()` is a classmethod that returns True if this backend can
    # deliver notifications in the current environment. Called once at startup
    # by `detect()` — never at notification time.
    @classmethod
    def available(cls) -> bool: ...

    # Deliver a notification. Implementations must not raise — swallow or log
    # failures silently so a broken notifier never crashes the daemon.
    def send(self, title: str, body: str) -> None: ...


# TODO: add a SoundNotifier backend that plays a sound alongside the visual notification.
class MsgExeNotifier:
    """Windows dialog via msg.exe. Works from WSL2."""

    @classmethod
    def available(cls) -> bool:
        return shutil.which("msg.exe") is not None

    def send(self, title: str, body: str) -> None:
        try:
            subprocess.run(
                ["msg.exe", "*", f"{title}: {body}"],
                check=False,
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


class NotifySendNotifier:
    """Desktop notification via notify-send. Works on native Linux with a DE."""

    @classmethod
    def available(cls) -> bool:
        return shutil.which("notify-send") is not None

    def send(self, title: str, body: str) -> None:
        try:
            subprocess.run(
                ["notify-send", "--app-name=Pomodoro", title, body],
                check=False,
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


class BellNotifier:
    """Terminal bell via /dev/pts/*. Always available as a last resort.

    The daemon redirects stdio to /dev/null, so we write directly to every
    accessible pts device instead of printing to stdout.
    """

    @classmethod
    def available(cls) -> bool:
        return True

    def send(self, title: str, body: str) -> None:
        for pts in glob.glob("/dev/pts/[0-9]*"):
            try:
                with open(pts, "w") as f:
                    f.write("\a")
            except OSError:
                continue


class CompositeNotifier:
    """Runs a list of notifiers in order. All are called unconditionally so
    the user gets every delivery channel that is available (e.g. bell + msg)."""

    def __init__(self, notifiers: list[Notifier]) -> None:
        self._notifiers = notifiers

    def send(self, title: str, body: str) -> None:
        for notifier in self._notifiers:
            notifier.send(title, body)


# To add a new backend: implement `available()` and `send()`, then add it here.
_BACKENDS: list[type[Notifier]] = [
    MsgExeNotifier,
    NotifySendNotifier,
    BellNotifier,
]


def detect() -> Notifier:
    """Return a CompositeNotifier containing all backends available in the
    current environment. BellNotifier is always included as a fallback."""
    return CompositeNotifier([cls() for cls in _BACKENDS if cls.available()])

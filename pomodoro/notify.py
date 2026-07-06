from __future__ import annotations

import base64
import glob
import shutil
import subprocess
import threading
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


# Real WinRT toast notifications (Action Center cards) were tried first, but
# proved undeliverable: WSL-spawned Windows processes hit a session/identity
# boundary that silently drops toasts before they ever reach the Action
# Center - confirmed even for genuinely registered AUMIDs (Explorer, Windows
# Terminal), and independent of elevation or session ID (both matched
# explorer.exe's). A MessageBox dialog uses the same raw-window mechanism as
# msg.exe, which *is* provably deliverable from this context - it just gets a
# real custom title instead of msg.exe's fixed "Message from <host> at <time>".
#
# Values are embedded as single-quoted PowerShell string literals (escaped by
# _ps_escape) and shipped via -EncodedCommand rather than as trailing
# -Command args - PowerShell doesn't cleanly bind those to $args for a
# multi-statement script, it re-appends the raw text as a second top-level
# command instead, which silently corrupts whichever value lands last.
_MESSAGEBOX_TEMPLATE = """
Add-Type -AssemblyName System.Windows.Forms > $null
[System.Windows.Forms.MessageBox]::Show('{body}', '{title}', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information) > $null
"""


def _ps_escape(value: str) -> str:
    """Escape a value for embedding in a single-quoted PowerShell string literal."""
    return value.replace("'", "''")


class MessageBoxNotifier:
    """Windows dialog via System.Windows.Forms.MessageBox, run through PowerShell.

    Works from WSL2. The Information icon triggers Windows' standard
    notification chime, so this covers sound too - no separate backend needed.

    Launched via Popen rather than run: MessageBox.Show blocks until the user
    clicks OK (which may be much later, or never), and that wait must happen
    in the detached PowerShell process, not on the daemon's thread. A reaper
    thread still calls wait() on it eventually so the child doesn't linger as
    a zombie once it exits.
    """

    @classmethod
    def available(cls) -> bool:
        return shutil.which("powershell.exe") is not None

    def send(self, title: str, body: str) -> None:
        script = _MESSAGEBOX_TEMPLATE.format(title=_ps_escape(title), body=_ps_escape(body))
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        try:
            proc = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Sta", "-EncodedCommand", encoded],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return
        threading.Thread(target=proc.wait, daemon=True).start()


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
    MessageBoxNotifier,
    NotifySendNotifier,
    BellNotifier,
]


def detect() -> Notifier:
    """Return a CompositeNotifier containing all backends available in the
    current environment. BellNotifier is always included as a fallback."""
    return CompositeNotifier([cls() for cls in _BACKENDS if cls.available()])

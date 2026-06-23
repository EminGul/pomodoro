from __future__ import annotations

import json
import socket as _socket
import subprocess
from pathlib import Path

# Candidate locations for Windows mpv, in priority order.
# The shinchiro winget build does not add itself to PATH.
_WINDOWS_MPV_CANDIDATES = [
    Path("/mnt/c/Program Files/MPV Player/mpv.exe"),
    Path("/mnt/c/Program Files/mpv/mpv.exe"),
]

_IPC_PIPE_NAME = "mpv-pomodoro"
_IPC_SOCK_PATH = Path("/tmp/mpv-pomodoro.sock")


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _find_windows_ytdlp() -> str | None:
    """Return the Windows path to yt-dlp.exe, preferring the newest install.

    WinGet packages take priority over PATH because the PATH entry may be an
    older pip-installed version that fails to decrypt YouTube signatures.
    """
    winget_root = Path("/mnt/c/Users")
    for candidate in winget_root.glob(
        "*/AppData/Local/Microsoft/WinGet/Packages/yt-dlp.yt-dlp*/yt-dlp.exe"
    ):
        parts = candidate.parts  # ('/', 'mnt', 'c', 'Users', ...)
        win_path = parts[2].upper() + ":/" + "/".join(parts[3:])
        return win_path

    try:
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-Command",
                "(Get-Command yt-dlp -ErrorAction SilentlyContinue).Source",
            ],
            capture_output=True, text=True, timeout=5,
        )
        path = result.stdout.strip()
        return path if path else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _resolve_mpv() -> tuple[str, str | None, bool]:
    """Return (mpv_executable, windows_ytdlp_path_or_None, is_windows_mpv).

    On WSL, prefers the Windows mpv.exe for native WASAPI audio.
    Falls back to the system mpv on plain Linux or if not found.
    """
    if not _is_wsl():
        return "mpv", None, False

    mpv_path = next((p for p in _WINDOWS_MPV_CANDIDATES if p.exists()), None)
    if mpv_path is None:
        return "mpv", None, False

    return str(mpv_path), _find_windows_ytdlp(), True


# Resolved once at import time — avoids repeated disk reads and a blocking
# PowerShell call on every Player instantiation.
_MPV_CMD, _YTDLP_PATH, _USING_WINDOWS_MPV = _resolve_mpv()


class Player:
    def __init__(self, volume: int = 100) -> None:
        self._proc: subprocess.Popen | None = None
        self.mpv_available: bool = True
        self._volume = max(0, min(volume, 100))
        self._mpv_cmd = _MPV_CMD
        self._ytdlp_path = _YTDLP_PATH
        self._using_windows_mpv = _USING_WINDOWS_MPV

    def play(self, urls: list[str], shuffle: bool = False, loop: bool = False) -> None:
        self.stop()
        if not urls:
            return
        ipc_arg = (
            f"--input-ipc-server={_IPC_PIPE_NAME}"
            if self._using_windows_mpv
            else f"--input-ipc-server={_IPC_SOCK_PATH}"
        )
        cmd = [self._mpv_cmd, "--no-video", "--really-quiet", f"--volume={self._volume}", ipc_arg]
        if self._ytdlp_path:
            cmd.append(f"--script-opts=ytdl_hook-ytdl_path={self._ytdlp_path}")
        if shuffle:
            cmd.append("--shuffle")
        if loop:
            cmd.append("--loop-playlist")
        cmd.extend(urls)
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.mpv_available = True
        except FileNotFoundError:
            self.mpv_available = False

    def pause_playback(self) -> None:
        if self.is_playing:
            self._mpv_command({"command": ["set_property", "pause", True]})

    def resume_playback(self) -> None:
        if self.is_playing:
            self._mpv_command({"command": ["set_property", "pause", False]})

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._kill_proc()
        self._proc = None

    def _kill_proc(self) -> None:
        # Windows processes launched from WSL ignore SIGTERM/SIGKILL.
        # proc.pid is a Linux stub PID, not the Windows PID, so /PID won't
        # work — kill by image name instead.
        if self._using_windows_mpv:
            try:
                subprocess.run(
                    ["taskkill.exe", "/IM", "mpv.exe", "/F"],
                    capture_output=True, timeout=5,
                )
                return
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()

    def _mpv_command(self, command: dict) -> None:
        if self._using_windows_mpv:
            self._mpv_command_pipe(command)
        else:
            self._mpv_command_unix(command)

    def _mpv_command_pipe(self, command: dict) -> None:
        payload = json.dumps(command)
        ps_script = (
            f"$p = New-Object System.IO.Pipes.NamedPipeClientStream('.', '{_IPC_PIPE_NAME}', "
            f"[System.IO.Pipes.PipeDirection]::InOut); "
            f"$p.Connect(2000); "
            f"$w = New-Object System.IO.StreamWriter($p); "
            f"$w.AutoFlush = $true; "
            f"$w.WriteLine('{payload}'); "
            f"$p.Close()"
        )
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_script],
                capture_output=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def _mpv_command_unix(self, command: dict) -> None:
        try:
            with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(str(_IPC_SOCK_PATH))
                s.sendall((json.dumps(command) + "\n").encode())
        except OSError:
            pass

    @property
    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

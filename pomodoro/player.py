from __future__ import annotations

import json
import socket as _socket
import subprocess
import time
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


def _parse_ipc_response(lines: list[str], request_id: int) -> str | None:
    """Pick the `data` value out of the mpv IPC reply matching `request_id`."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("request_id") == request_id and "data" in obj and obj["data"] is not None:
            return obj["data"]
    return None


def _ipc_send_unix(command: dict, request_id: int | None = None) -> list[str]:
    """Send `command` over the Unix IPC socket.

    Fire-and-forget when `request_id` is None. Otherwise reads until a reply
    matching `request_id` arrives or the deadline elapses, so an unsolicited
    mpv event line can't be mistaken for "no reply".
    """
    try:
        with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(str(_IPC_SOCK_PATH))
            s.sendall((json.dumps(command) + "\n").encode())
            if request_id is None:
                return []
            buf = b""
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                lines = buf.decode(errors="replace").splitlines()
                if _parse_ipc_response(lines, request_id) is not None:
                    return lines
            return buf.decode(errors="replace").splitlines()
    except OSError:
        return []


def _ipc_send_pipe(command: dict, request_id: int | None = None) -> list[str]:
    """Send `command` over the Windows named-pipe IPC channel.

    Fire-and-forget when `request_id` is None. Otherwise polls for a reply
    line whose `request_id` matches exactly (the `(?!\\d)` guard stops "1"
    from matching a reply for id "10", "19", etc).
    """
    payload = json.dumps(command)
    if request_id is None:
        ps_script = (
            f"$p = New-Object System.IO.Pipes.NamedPipeClientStream('.', '{_IPC_PIPE_NAME}', "
            f"[System.IO.Pipes.PipeDirection]::InOut); "
            f"$p.Connect(2000); "
            f"$w = New-Object System.IO.StreamWriter($p); "
            f"$w.AutoFlush = $true; "
            f"$w.WriteLine('{payload}'); "
            f"$p.Close()"
        )
    else:
        ps_script = (
            f"$p = New-Object System.IO.Pipes.NamedPipeClientStream('.', '{_IPC_PIPE_NAME}', "
            f"[System.IO.Pipes.PipeDirection]::InOut); "
            f"$p.Connect(2000); "
            f"$w = New-Object System.IO.StreamWriter($p); $w.AutoFlush = $true; "
            f"$r = New-Object System.IO.StreamReader($p); "
            f"$w.WriteLine('{payload}'); "
            f"for ($i = 0; $i -lt 20; $i++) {{ "
            f"$line = $r.ReadLine(); "
            f"if ($line -match '\"request_id\":{request_id}(?!\\d)') {{ Write-Output $line; break }} "
            f"}}; "
            f"$p.Close()"
        )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return result.stdout.splitlines()


def fetch_title(url: str) -> str | None:
    """Best-effort video title lookup via yt-dlp. Returns None on any failure."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--get-title", "--no-playlist", url],
            capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        result = None

    if result is None or result.returncode != 0:
        if not (_is_wsl() and _YTDLP_PATH):
            return None
        # Fall back to the Windows yt-dlp install used for WSL audio; pass the
        # exe path and URL as $args so neither is interpolated into the
        # PowerShell command string.
        try:
            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-Command",
                    "& $args[0] --get-title --no-playlist $args[1]",
                    _YTDLP_PATH, url,
                ],
                capture_output=True, text=True, timeout=15,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else None


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

    def current_title(self) -> str | None:
        """The title of the track mpv is currently playing, or None."""
        if not self.is_playing:
            return None
        return self._get_property("media-title")

    def _get_property(self, prop: str) -> str | None:
        request_id = 1
        command = {"command": ["get_property", prop], "request_id": request_id}
        lines = self._ipc_send(command, request_id)
        return _parse_ipc_response(lines, request_id)

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
        self._ipc_send(command)

    def _ipc_send(self, command: dict, request_id: int | None = None) -> list[str]:
        if self._using_windows_mpv:
            return _ipc_send_pipe(command, request_id)
        return _ipc_send_unix(command, request_id)

    @property
    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

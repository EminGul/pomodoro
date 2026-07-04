from __future__ import annotations

import os
import signal
import socket
import threading
import time

from pomodoro.config import Config
from pomodoro.notify import Notifier, detect
from pomodoro.player import Player
from pomodoro.state import SOCK_FILE, clear_state, write_pid, write_state
from pomodoro.timer import SessionType, TimerState


class Daemon:
    def __init__(self, config: Config, notifier: Notifier | None = None) -> None:
        self._config = config
        self._notifier = notifier or detect()
        self._player = Player(volume=config.volume)
        self._state = TimerState.initial(
            config.work_secs, config.sessions_before_long_break
        )
        self._running = True
        self._paused = False
        self._lock = threading.Lock()

    def run(self) -> None:
        write_pid(os.getpid())
        signal.signal(signal.SIGTERM, self._handle_stop)
        signal.signal(signal.SIGINT, self._handle_stop)

        socket_thread = threading.Thread(target=self._serve_socket, daemon=True)
        socket_thread.start()

        self._start_session()

        try:
            while self._running:
                time.sleep(1)
                with self._lock:
                    if self._paused:
                        continue
                    ended = self._state.tick()
                    if ended:
                        self._end_session()
                    else:
                        write_state(self._state, self._player.is_playing, self._player.mpv_available)
        finally:
            self._player.stop()
            clear_state()

    def _start_session(self) -> None:
        if self._config.song_urls:
            if self._state.session_type == SessionType.WORK:
                if self._player.is_playing:
                    self._player.resume_playback()
                else:
                    self._player.play(self._config.song_urls, self._config.shuffle, self._config.loop)
            else:
                if self._player.is_playing:
                    self._player.pause_playback()
        write_state(self._state, self._player.is_playing, self._player.mpv_available, self._paused)

    def _end_session(self) -> None:
        self._config = Config.load()
        stype = self._state.session_type
        if stype == SessionType.WORK:
            self._notifier.send("Pomodoro complete", "Time for a break.")
        elif stype == SessionType.LONG_BREAK:
            self._notifier.send("Long break over", "Ready for the next round.")
        else:
            self._notifier.send("Break over", "Back to work.")
        self._state.advance(
            self._config.work_secs,
            self._config.short_break_secs,
            self._config.long_break_secs,
        )
        self._start_session()

    def _pause(self) -> None:
        with self._lock:
            self._paused = True
            self._player.pause_playback()
            write_state(self._state, self._player.is_playing, self._player.mpv_available, paused=True)

    def _resume(self) -> None:
        with self._lock:
            self._paused = False
            self._start_session()

    def _skip(self) -> None:
        with self._lock:
            self._paused = False
            self._player.stop()
            self._state.advance(
                self._config.work_secs,
                self._config.short_break_secs,
                self._config.long_break_secs,
            )
            self._start_session()

    def _handle_stop(self, signum, frame) -> None:  # noqa: ANN001
        self._running = False

    def _serve_socket(self) -> None:
        SOCK_FILE.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as srv:
            srv.bind(str(SOCK_FILE))
            srv.listen(5)
            srv.settimeout(1)
            while self._running:
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                with conn:
                    cmd = conn.recv(64).decode().strip()
                    if cmd == "skip":
                        self._skip()
                        conn.sendall(b"ok\n")
                    elif cmd == "pause":
                        self._pause()
                        conn.sendall(b"ok\n")
                    elif cmd == "resume":
                        self._resume()
                        conn.sendall(b"ok\n")
                    elif cmd == "stop":
                        self._running = False
                        conn.sendall(b"ok\n")


def daemonize(config: Config) -> None:
    """Double-fork to detach the daemon from the calling terminal."""
    if os.fork() > 0:
        return
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    os.close(devnull)
    Daemon(config).run()
    os._exit(0)

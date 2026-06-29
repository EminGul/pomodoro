from __future__ import annotations

import os
import socket
import sys
import time

import click

from pomodoro import daemon as daemon_module
from pomodoro.config import PRESETS, Config
from pomodoro.state import SOCK_FILE, read_pid, read_state


def _daemon_running() -> bool:
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _send(cmd: str) -> str | None:
    if not SOCK_FILE.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect(str(SOCK_FILE))
            s.sendall(cmd.encode() + b"\n")
            return s.recv(64).decode().strip()
    except (OSError, socket.timeout):
        return None


def _fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def _fmt_mins(secs: int) -> str:
    return f"{secs // 60} min"


@click.group()
def main() -> None:
    """Pomodoro timer with YouTube music streaming."""


@main.command()
@click.option("--preset", type=click.Choice(list(PRESETS)), default=None, help="Named duration preset")
@click.option("--work", type=int, default=None, help="Work duration in minutes")
@click.option("--short-break", "short_break", type=int, default=None, help="Short break in minutes")
@click.option("--long-break", "long_break", type=int, default=None, help="Long break in minutes")
@click.option("--sessions", type=int, default=None, help="Work sessions before long break")
@click.option("--volume", type=click.IntRange(0, 100), default=None, help="Music volume (0-100)")
def start(preset: str | None, work: int | None, short_break: int | None, long_break: int | None, sessions: int | None, volume: int | None) -> None:
    """Start the Pomodoro timer daemon."""
    if _daemon_running():
        click.echo("Daemon already running. Use 'pomodoro stop' first.")
        sys.exit(1)

    config = Config.load()
    if preset:
        config.apply_preset(preset)
    if work is not None:
        config.work_secs = work * 60
    if short_break is not None:
        config.short_break_secs = short_break * 60
    if long_break is not None:
        config.long_break_secs = long_break * 60
    if sessions is not None:
        config.sessions_before_long_break = sessions
    if volume is not None:
        config.volume = volume
    config.save()

    daemon_module.daemonize(config)
    time.sleep(0.5)

    if _daemon_running():
        click.echo(
            f"Started.  work={_fmt_time(config.work_secs)}  "
            f"short-break={_fmt_time(config.short_break_secs)}  "
            f"long-break={_fmt_time(config.long_break_secs)}  "
            f"sessions={config.sessions_before_long_break}"
        )
    else:
        click.echo("Failed to start daemon.", err=True)
        sys.exit(1)


@main.command()
def stop() -> None:
    """Stop the Pomodoro timer daemon."""
    result = _send("stop")
    if result == "ok":
        click.echo("Stopped.")
    else:
        click.echo("Daemon not running.", err=True)


@main.command()
def skip() -> None:
    """Skip the current session."""
    result = _send("skip")
    if result == "ok":
        click.echo("Skipped.")
    else:
        click.echo("Daemon not running.", err=True)


@main.command()
def pause() -> None:
    """Pause the timer and stop music."""
    result = _send("pause")
    if result == "ok":
        click.echo("Paused.")
    else:
        click.echo("Daemon not running.", err=True)


@main.command()
def resume() -> None:
    """Resume the timer and restart music."""
    result = _send("resume")
    if result == "ok":
        click.echo("Resumed.")
    else:
        click.echo("Daemon not running.", err=True)


@main.command()
def status() -> None:
    """Show current session and time remaining."""
    if not _daemon_running():
        click.echo("Daemon not running.")
        return

    state = read_state()
    if not state:
        click.echo("No state available.")
        return

    stype = state["session_type"].replace("_", " ").title()
    remaining = _fmt_time(state["seconds_remaining"])
    music = "yes" if state["music_playing"] else "no"
    done = state["total_work_sessions"]
    paused = state.get("paused", False)
    click.echo(f"Session:   {stype}{' (paused)' if paused else ''}")
    click.echo(f"Remaining: {remaining}")
    click.echo(f"Music:     {music}")
    click.echo(f"Completed: {done} work session(s)")
    if not state.get("mpv_available", True):
        click.echo("Warning:   mpv not found -- music is disabled. Install with: sudo apt install mpv", err=True)


@main.group()
def songs() -> None:
    """Manage the study playlist."""


@songs.command("add")
@click.argument("url")
def songs_add(url: str) -> None:
    """Add a YouTube URL to the playlist."""
    config = Config.load()
    config.songs.append(url)
    config.save()
    click.echo(f"Added. Playlist has {len(config.songs)} song(s).")


@songs.command("list")
def songs_list() -> None:
    """List all songs in the playlist."""
    config = Config.load()
    if not config.songs:
        click.echo("Playlist is empty.")
        return
    for i, url in enumerate(config.songs):
        click.echo(f"{i}  {url}")


@songs.command("remove")
@click.argument("index", type=int)
def songs_remove(index: int) -> None:
    """Remove a song by index (see 'songs list')."""
    config = Config.load()
    if index < 0 or index >= len(config.songs):
        click.echo(f"Index {index} out of range (0-{len(config.songs) - 1}).", err=True)
        sys.exit(1)
    removed = config.songs.pop(index)
    config.save()
    click.echo(f"Removed: {removed}")


@songs.command("shuffle")
@click.argument("state", type=click.Choice(["on", "off"]))
def songs_shuffle(state: str) -> None:
    """Enable or disable shuffle for the playlist."""
    config = Config.load()
    config.shuffle = state == "on"
    config.save()
    click.echo(f"Shuffle: {state}")


@main.command()
@click.argument("level", type=click.IntRange(0, 100))
def volume(level: int) -> None:
    """Set music volume (0-100). Takes effect on next start."""
    config = Config.load()
    config.volume = level
    config.save()
    click.echo(f"Volume: {level}")


@main.command()
@click.argument("state", type=click.Choice(["on", "off"]))
def loop(state: str) -> None:
    """Enable or disable looping the playlist."""
    config = Config.load()
    config.loop = state == "on"
    config.save()
    click.echo(f"Loop: {state}")


@main.command()
def restart() -> None:
    """Stop the running daemon (if any) and start a fresh one."""
    if _daemon_running():
        _send("stop")
        time.sleep(0.5)
    config = Config.load()
    daemon_module.daemonize(config)
    time.sleep(0.5)
    if _daemon_running():
        click.echo("Restarted.")
    else:
        click.echo("Failed to start daemon.", err=True)
        sys.exit(1)


@main.group()
def config() -> None:
    """View or change timer settings."""


@config.command("show")
def config_show() -> None:
    """Print all current settings."""
    cfg = Config.load()
    n = cfg.sessions_before_long_break
    click.echo(f"Cycle: {n} work sessions, then a long break.")
    click.echo("")
    click.echo(f"work          {cfg.work_secs // 60} min")
    click.echo(f"short-break   {cfg.short_break_secs // 60} min")
    click.echo(f"long-break    {cfg.long_break_secs // 60} min")
    click.echo(f"sessions      {n}")
    click.echo(f"volume        {cfg.volume}")
    click.echo(f"shuffle       {'on' if cfg.shuffle else 'off'}")
    click.echo(f"loop          {'on' if cfg.loop else 'off'}")
    click.echo(f"songs         {len(cfg.songs)}")


_CONFIG_KEYS = {
    "work", "short-break", "long-break", "sessions", "volume", "shuffle", "loop", "preset",
}


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a single timer setting by name.

    Keys: work, short-break, long-break (minutes), sessions (count),
    volume (0-100), shuffle (on/off), loop (on/off), preset (name).

    If the daemon is running, changes take effect at the next session
    boundary. Run 'pomodoro restart' to apply them immediately.
    """
    if key not in _CONFIG_KEYS:
        click.echo(
            f"Unknown key '{key}'. Valid keys: {', '.join(sorted(_CONFIG_KEYS))}",
            err=True,
        )
        sys.exit(1)

    cfg = Config.load()

    try:
        if key == "work":
            cfg.work_secs = _parse_minutes(key, value)
        elif key == "short-break":
            cfg.short_break_secs = _parse_minutes(key, value)
        elif key == "long-break":
            cfg.long_break_secs = _parse_minutes(key, value)
        elif key == "sessions":
            cfg.sessions_before_long_break = _parse_int(key, value, min_val=1)
        elif key == "volume":
            cfg.volume = _parse_int(key, value, min_val=0, max_val=100)
        elif key == "shuffle":
            cfg.shuffle = _parse_on_off(key, value)
        elif key == "loop":
            cfg.loop = _parse_on_off(key, value)
        elif key == "preset":
            cfg.apply_preset(value)
    except (ValueError, click.BadParameter) as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    cfg.save()

    if key == "work":
        click.echo(f"work = {_fmt_mins(cfg.work_secs)}")
    elif key == "short-break":
        click.echo(f"short-break = {_fmt_mins(cfg.short_break_secs)}")
    elif key == "long-break":
        click.echo(f"long-break = {_fmt_mins(cfg.long_break_secs)}")
    elif key == "sessions":
        n = cfg.sessions_before_long_break
        click.echo(f"sessions = {n}  (long break after every {n} work sessions)")
    elif key == "volume":
        click.echo(f"volume = {cfg.volume}")
    elif key == "shuffle":
        click.echo(f"shuffle = {'on' if cfg.shuffle else 'off'}")
    elif key == "loop":
        click.echo(f"loop = {'on' if cfg.loop else 'off'}")
    elif key == "preset":
        click.echo(
            f"preset '{value}' applied: "
            f"work = {_fmt_mins(cfg.work_secs)}, "
            f"short-break = {_fmt_mins(cfg.short_break_secs)}, "
            f"long-break = {_fmt_mins(cfg.long_break_secs)}"
        )

    if _daemon_running():
        click.echo("Note: takes effect at the next session boundary. Run 'pomodoro restart' to apply now.")


def _parse_minutes(key: str, value: str) -> int:
    try:
        minutes = int(value)
    except ValueError:
        raise ValueError(f"'{key}' expects a whole number of minutes, got '{value}'.")
    if minutes < 1:
        raise ValueError(f"'{key}' must be at least 1 minute.")
    return minutes * 60


def _parse_int(key: str, value: str, min_val: int | None = None, max_val: int | None = None) -> int:
    try:
        n = int(value)
    except ValueError:
        raise ValueError(f"'{key}' expects an integer, got '{value}'.")
    if min_val is not None and n < min_val:
        raise ValueError(f"'{key}' must be >= {min_val}.")
    if max_val is not None and n > max_val:
        raise ValueError(f"'{key}' must be <= {max_val}.")
    return n


def _parse_on_off(key: str, value: str) -> bool:
    if value not in ("on", "off"):
        raise ValueError(f"'{key}' expects 'on' or 'off', got '{value}'.")
    return value == "on"

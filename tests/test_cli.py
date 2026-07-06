from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from pomodoro.cli import _MAX_TITLE_WIDTH, _render_status, _wait_for_state, _watch_loop, main
from pomodoro.config import Config


def _plain(lines):
    """Strip ANSI styling so assertions can match on plain text."""
    return [click.unstyle(line) for line in lines]


def _state(**overrides):
    base = {
        "session_type": "work",
        "seconds_remaining": 90,
        "total_work_sessions": 2,
        "music_playing": True,
        "paused": False,
        "mpv_available": True,
        "song_title": None,
    }
    base.update(overrides)
    return base


def test_render_status_basic_fields():
    lines = _plain(_render_status(_state()))
    assert lines[0] == "WORK"
    assert lines[2].startswith("Time left  01:30")
    assert lines[3] == "Music      yes"


def test_render_status_colors_by_session_type():
    work_line = _render_status(_state(session_type="work"))[0]
    break_line = _render_status(_state(session_type="short_break"))[0]
    assert "\x1b[32m" in work_line  # green
    assert "\x1b[33m" in break_line  # yellow


def test_render_status_shows_progress_bar_at_start_and_end():
    start_line = _plain(_render_status(_state(seconds_remaining=100, session_total_seconds=100)))[2]
    end_line = _plain(_render_status(_state(seconds_remaining=0, session_total_seconds=100)))[2]
    assert "0%" in start_line
    assert "100%" in end_line


def test_render_status_shows_song_title_when_music_playing():
    lines = _plain(_render_status(_state(song_title="Lofi Beats to Study To")))
    assert "Playing    Lofi Beats to Study To" in lines


def test_render_status_hides_song_title_when_music_not_playing():
    lines = _plain(_render_status(_state(music_playing=False, song_title="Lofi Beats")))
    assert not any(line.startswith("Playing") for line in lines)


def test_render_status_hides_song_title_when_none():
    lines = _plain(_render_status(_state(song_title=None)))
    assert not any(line.startswith("Playing") for line in lines)


def test_render_status_shows_paused_marker():
    lines = _plain(_render_status(_state(paused=True)))
    assert lines[0] == "WORK  (PAUSED)"


def test_render_status_warns_when_mpv_missing():
    lines = _plain(_render_status(_state(mpv_available=False)))
    assert any("mpv not found" in line for line in lines)


def test_render_status_truncates_long_song_title():
    long_title = "A" * 100
    lines = _plain(_render_status(_state(song_title=long_title)))
    playing_line = next(line for line in lines if line.startswith("Playing"))
    title_shown = playing_line[len("Playing    "):]
    assert len(title_shown) <= _MAX_TITLE_WIDTH
    assert title_shown.endswith("...")


def test_render_status_does_not_truncate_short_song_title():
    lines = _plain(_render_status(_state(song_title="Short Title")))
    assert "Playing    Short Title" in lines


def test_render_status_shows_unknown_progress_when_total_missing():
    # session_total_seconds is absent entirely from _state()'s base dict,
    # simulating state.json written by a daemon started before this field
    # existed. Must not be confused with a legitimate 0%, which would freeze
    # the bar at 0% for that daemon's whole remaining life.
    lines = _plain(_render_status(_state()))
    assert "restart the daemon" in lines[2]
    assert "%" not in lines[2]


def test_render_status_shows_zero_percent_when_total_explicitly_present():
    lines = _plain(_render_status(_state(seconds_remaining=100, session_total_seconds=100)))
    assert "0%" in lines[2]


def test_wait_for_state_returns_immediately_when_state_present():
    with patch("pomodoro.cli.read_state", return_value={"ok": True}):
        assert _wait_for_state(timeout=1.0) == {"ok": True}


def test_wait_for_state_retries_until_available():
    responses = iter([None, None, {"ok": True}])
    with patch("pomodoro.cli.read_state", side_effect=lambda: next(responses)):
        assert _wait_for_state(timeout=2.0) == {"ok": True}


def test_wait_for_state_gives_up_after_timeout():
    with patch("pomodoro.cli.read_state", return_value=None):
        assert _wait_for_state(timeout=0.2) is None


def test_watch_loop_shows_watch_mode_header(capsys):
    with (
        patch("pomodoro.cli.sys.stdin.isatty", return_value=False),
        patch("pomodoro.cli.time.sleep", side_effect=KeyboardInterrupt),
        patch("pomodoro.cli._daemon_running", return_value=False),
    ):
        _watch_loop(_state())
    lines = _plain(capsys.readouterr().out.splitlines())
    idx = lines.index("Watch Mode: Press q to quit")
    assert lines[idx - 1] == ""
    assert lines[idx + 1] == ""


def test_watch_loop_stops_daemon_on_ctrl_c(capsys):
    with (
        patch("pomodoro.cli.sys.stdin.isatty", return_value=False),
        patch("pomodoro.cli.time.sleep", side_effect=KeyboardInterrupt),
        patch("pomodoro.cli._daemon_running", return_value=True),
        patch("pomodoro.cli._send", return_value="ok") as mock_send,
    ):
        _watch_loop(_state())
    mock_send.assert_called_once_with("stop")
    assert "Stopped." in capsys.readouterr().out


def test_watch_loop_reports_failure_if_daemon_wont_stop(capsys):
    with (
        patch("pomodoro.cli.sys.stdin.isatty", return_value=False),
        patch("pomodoro.cli.time.sleep", side_effect=KeyboardInterrupt),
        patch("pomodoro.cli._daemon_running", return_value=True),
        patch("pomodoro.cli._send", return_value=None),
    ):
        _watch_loop(_state())
    assert "Failed to stop daemon." in capsys.readouterr().err


def test_watch_loop_skips_stop_when_daemon_already_gone(capsys):
    with (
        patch("pomodoro.cli.sys.stdin.isatty", return_value=False),
        patch("pomodoro.cli.time.sleep", side_effect=KeyboardInterrupt),
        patch("pomodoro.cli._daemon_running", return_value=False),
        patch("pomodoro.cli._send") as mock_send,
    ):
        _watch_loop(_state())
    mock_send.assert_not_called()


@pytest.fixture
def isolated_config(tmp_path):
    config_file = tmp_path / "config.json"
    with (
        patch("pomodoro.config.CONFIG_DIR", tmp_path),
        patch("pomodoro.config.CONFIG_FILE", config_file),
    ):
        yield


@pytest.fixture
def runner():
    return CliRunner()


def _add_playlist(name: str, make_active: bool = True) -> None:
    """Set up a second playlist directly, since creating/switching now lives in the editor."""
    config = Config.load()
    config.playlists[name] = []
    if make_active:
        config.active_playlist = name
    config.save()


def test_playlist_add_targets_active_playlist(isolated_config, runner):
    _add_playlist("gym")
    runner.invoke(main, ["playlist", "add", "https://youtube.com/watch?v=abc", "Song A"])

    result = runner.invoke(main, ["playlist", "list"])
    assert "Song A" in result.output

    config = Config.load()
    config.active_playlist = "default"
    config.save()
    result = runner.invoke(main, ["playlist", "list"])
    assert "Playlist 'default' is empty." in result.output


def test_playlist_all_marks_the_active_playlist(isolated_config, runner):
    _add_playlist("gym")
    result = runner.invoke(main, ["playlist", "all"])
    assert "* gym" in result.output
    assert "  default" in result.output


def test_playlist_delete_switches_active_when_needed(isolated_config, runner):
    _add_playlist("gym")
    result = runner.invoke(main, ["playlist", "delete", "gym"])
    assert result.exit_code == 0
    assert "Switched to 'default'" in result.output

    result = runner.invoke(main, ["playlist", "all"])
    assert "gym" not in result.output


def test_playlist_delete_last_playlist_fails(isolated_config, runner):
    result = runner.invoke(main, ["playlist", "delete", "default"])
    assert result.exit_code != 0
    assert "Cannot delete the only playlist" in result.output


def test_config_show_playlist_count_not_inflated_by_dangling_active_playlist(isolated_config, runner):
    # active_playlist pointing at a name not yet in playlists is a valid,
    # intentional state (the editor's not-yet-created carousel slot).
    # Reading song_urls to build this line must not silently materialize
    # that name and then count it as a real playlist in the same breath.
    config = Config.load()
    config.active_playlist = "Playlist 2"
    config.save()

    result = runner.invoke(main, ["config", "show"])

    assert "1 playlist(s) total" in result.output
    assert Config.load().playlists == {"default": []}


def test_playlist_edit_notes_dangling_active_playlist_on_exit(isolated_config, runner):
    config = Config.load()
    config.active_playlist = "Playlist 2"
    config.save()

    with patch("pomodoro.cli.run_editor"):
        result = runner.invoke(main, ["playlist", "edit"])

    assert "doesn't exist yet" in result.output


def test_playlist_edit_silent_when_active_playlist_is_real(isolated_config, runner):
    with patch("pomodoro.cli.run_editor"):
        result = runner.invoke(main, ["playlist", "edit"])

    assert "doesn't exist yet" not in result.output


def test_playlist_edit_prints_exited_on_ctrl_c(isolated_config, runner):
    with patch("pomodoro.cli.run_editor", side_effect=KeyboardInterrupt):
        result = runner.invoke(main, ["playlist", "edit"])

    assert "Exited." in result.output
    assert "Aborted" not in result.output
    assert result.exit_code == 0

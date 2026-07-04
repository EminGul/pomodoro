from unittest.mock import patch

from pomodoro.cli import _MAX_TITLE_WIDTH, _render_status, _wait_for_state


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
    lines = _render_status(_state())
    assert lines[0] == "Session:   Work"
    assert lines[1] == "Remaining: 01:30"
    assert lines[2] == "Music:     yes"


def test_render_status_shows_song_title_when_music_playing():
    lines = _render_status(_state(song_title="Lofi Beats to Study To"))
    assert "Playing:   Lofi Beats to Study To" in lines


def test_render_status_hides_song_title_when_music_not_playing():
    lines = _render_status(_state(music_playing=False, song_title="Lofi Beats"))
    assert not any(line.startswith("Playing:") for line in lines)


def test_render_status_hides_song_title_when_none():
    lines = _render_status(_state(song_title=None))
    assert not any(line.startswith("Playing:") for line in lines)


def test_render_status_shows_paused_marker():
    lines = _render_status(_state(paused=True))
    assert lines[0] == "Session:   Work (paused)"


def test_render_status_warns_when_mpv_missing():
    lines = _render_status(_state(mpv_available=False))
    assert any("mpv not found" in line for line in lines)


def test_render_status_truncates_long_song_title():
    long_title = "A" * 100
    lines = _render_status(_state(song_title=long_title))
    playing_line = next(line for line in lines if line.startswith("Playing:"))
    title_shown = playing_line[len("Playing:   "):]
    assert len(title_shown) <= _MAX_TITLE_WIDTH
    assert title_shown.endswith("...")


def test_render_status_does_not_truncate_short_song_title():
    lines = _render_status(_state(song_title="Short Title"))
    assert "Playing:   Short Title" in lines


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

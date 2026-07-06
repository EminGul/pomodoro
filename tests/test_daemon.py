import time
from types import SimpleNamespace

from pomodoro.config import Config
from pomodoro.daemon import Daemon
from pomodoro.playlist import Song
from pomodoro.timer import SessionType


class _NoopNotifier:
    def send(self, title: str, body: str) -> None:
        pass


def _make_daemon(**config_overrides) -> Daemon:
    config = Config(**config_overrides)
    return Daemon(config, notifier=_NoopNotifier())


def _set_playing(daemon: Daemon, playing: bool) -> None:
    daemon._player._proc = SimpleNamespace(poll=lambda: None) if playing else None


def test_is_music_active_requires_playing_work_and_unpaused():
    daemon = _make_daemon()
    _set_playing(daemon, True)
    daemon._state.session_type = SessionType.WORK
    daemon._paused = False
    assert daemon._is_music_active() is True


def test_is_music_active_false_during_break_even_if_process_alive():
    daemon = _make_daemon()
    _set_playing(daemon, True)
    daemon._state.session_type = SessionType.SHORT_BREAK
    daemon._paused = False
    assert daemon._is_music_active() is False


def test_is_music_active_false_when_user_paused():
    daemon = _make_daemon()
    _set_playing(daemon, True)
    daemon._state.session_type = SessionType.WORK
    daemon._paused = True
    assert daemon._is_music_active() is False


def test_is_music_active_false_when_process_dead():
    daemon = _make_daemon()
    _set_playing(daemon, False)
    daemon._state.session_type = SessionType.WORK
    daemon._paused = False
    assert daemon._is_music_active() is False


def test_refresh_song_title_clears_cache_when_not_playing():
    daemon = _make_daemon()
    daemon._current_song = "Stale Title"
    _set_playing(daemon, False)
    daemon._refresh_song_title()
    assert daemon._current_song is None


def test_refresh_song_title_throttles_within_poll_interval():
    daemon = _make_daemon()
    _set_playing(daemon, True)
    daemon._player.current_path = lambda: "Should Not Be Seen"
    daemon._current_song = "Old Title"
    daemon._last_song_query = time.time()
    daemon._refresh_song_title()
    assert daemon._current_song == "Old Title"


def test_refresh_song_title_updates_on_successful_query():
    daemon = _make_daemon()
    _set_playing(daemon, True)
    daemon._song_names = {"u1": "New Title"}
    daemon._player.current_path = lambda: "u1"
    daemon._last_song_query = 0.0
    daemon._refresh_song_title()
    assert daemon._current_song == "New Title"


def test_refresh_song_title_falls_back_to_path_when_not_in_playlist():
    daemon = _make_daemon()
    _set_playing(daemon, True)
    daemon._song_names = {}
    daemon._player.current_path = lambda: "https://youtube.com/watch?v=unknown"
    daemon._last_song_query = 0.0
    daemon._refresh_song_title()
    assert daemon._current_song == "https://youtube.com/watch?v=unknown"


def test_refresh_song_title_keeps_stale_value_on_failed_query():
    daemon = _make_daemon()
    _set_playing(daemon, True)
    daemon._player.current_path = lambda: None
    daemon._current_song = "Previous Title"
    daemon._last_song_query = 0.0
    daemon._refresh_song_title()
    assert daemon._current_song == "Previous Title"


def test_start_session_clears_stale_title_when_spawning_fresh_playback():
    daemon = _make_daemon()
    daemon._config.songs = [Song(url="u1", name="n1")]
    _set_playing(daemon, False)
    daemon._player.play = lambda *a, **kw: None
    daemon._current_song = "Previous Song From Before A Skip"
    daemon._last_song_query = time.time()

    daemon._start_session()

    assert daemon._current_song is None
    assert daemon._last_song_query == 0.0


def test_start_session_builds_song_names_from_playlist_on_fresh_playback():
    daemon = _make_daemon()
    daemon._config.songs = [Song(url="u1", name="Track One"), None, Song(url="u2", name="Track Two")]
    _set_playing(daemon, False)
    daemon._player.play = lambda *a, **kw: None

    daemon._start_session()

    assert daemon._song_names == {"u1": "Track One", "u2": "Track Two"}


def test_start_session_keeps_title_when_resuming_existing_playback():
    daemon = _make_daemon()
    daemon._config.songs = [Song(url="u1", name="n1")]
    _set_playing(daemon, True)
    daemon._player.resume_playback = lambda: None
    daemon._current_song = "Still Playing This"
    last_query = 12345.0
    daemon._last_song_query = last_query

    daemon._start_session()

    assert daemon._current_song == "Still Playing This"
    assert daemon._last_song_query == last_query


def test_start_session_refreshes_song_names_when_resuming_existing_playback():
    # A playlist edit made during a break (mpv only paused, not stopped) must
    # be picked up on resume -- previously _song_names was only rebuilt on a
    # fresh mpv spawn, so a rename made mid-break kept showing the old name
    # for the rest of that daemon's life.
    daemon = _make_daemon()
    daemon._song_names = {"u1": "Stale Name"}
    daemon._config.songs = [Song(url="u1", name="Renamed During Break")]
    _set_playing(daemon, True)
    daemon._player.resume_playback = lambda: None

    daemon._start_session()

    assert daemon._song_names == {"u1": "Renamed During Break"}

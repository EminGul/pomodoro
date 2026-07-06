import pytest
from unittest.mock import patch

from pomodoro.config import Config, PRESETS
from pomodoro.playlist import Song


def test_defaults():
    cfg = Config()
    assert cfg.work_secs == 25 * 60
    assert cfg.short_break_secs == 5 * 60
    assert cfg.long_break_secs == 15 * 60
    assert cfg.sessions_before_long_break == 4
    assert cfg.songs == []
    assert not cfg.shuffle


def test_apply_preset_classic():
    cfg = Config()
    cfg.apply_preset("classic")
    assert cfg.work_secs == PRESETS["classic"]["work"]
    assert cfg.short_break_secs == PRESETS["classic"]["short_break"]


def test_apply_preset_long():
    cfg = Config()
    cfg.apply_preset("long")
    assert cfg.work_secs == 50 * 60
    assert cfg.long_break_secs == 30 * 60


def test_apply_preset_short():
    cfg = Config()
    cfg.apply_preset("short")
    assert cfg.work_secs == 15 * 60


def test_apply_preset_test():
    cfg = Config()
    cfg.apply_preset("test")
    assert cfg.work_secs == 10
    assert cfg.short_break_secs == 5
    assert cfg.long_break_secs == 10


def test_apply_preset_unknown_raises():
    cfg = Config()
    with pytest.raises(ValueError, match="Unknown preset"):
        cfg.apply_preset("nonexistent")


def test_save_and_load(tmp_path):
    config_file = tmp_path / "config.json"
    with (
        patch("pomodoro.config.CONFIG_DIR", tmp_path),
        patch("pomodoro.config.CONFIG_FILE", config_file),
    ):
        cfg = Config(work_secs=30 * 60)
        cfg.songs = [Song(url="https://youtube.com/watch?v=abc", name="Track One"), None]
        cfg.save()
        loaded = Config.load()
    assert loaded.work_secs == 30 * 60
    assert loaded.songs == [Song(url="https://youtube.com/watch?v=abc", name="Track One"), None]
    assert loaded.song_urls == ["https://youtube.com/watch?v=abc"]


def test_songs_property_reads_and_writes_active_playlist():
    cfg = Config()
    cfg.playlists["work"] = [Song(url="u1", name="s1")]
    cfg.active_playlist = "work"
    assert cfg.songs == [Song(url="u1", name="s1")]
    cfg.songs = [Song(url="u2", name="s2")]
    assert cfg.playlists["work"] == [Song(url="u2", name="s2")]


def test_multiple_named_playlists_are_independent():
    cfg = Config()
    cfg.playlists["study"] = [Song(url="u1", name="s1")]
    cfg.playlists["gym"] = [Song(url="u2", name="s2")]
    cfg.active_playlist = "study"
    assert cfg.song_urls == ["u1"]
    cfg.active_playlist = "gym"
    assert cfg.song_urls == ["u2"]


def test_save_and_load_multiple_playlists(tmp_path):
    config_file = tmp_path / "config.json"
    with (
        patch("pomodoro.config.CONFIG_DIR", tmp_path),
        patch("pomodoro.config.CONFIG_FILE", config_file),
    ):
        cfg = Config()
        cfg.playlists["gym"] = [Song(url="u2", name="s2")]
        cfg.active_playlist = "gym"
        cfg.save()
        loaded = Config.load()
    assert loaded.active_playlist == "gym"
    assert set(loaded.playlists) == {"default", "gym"}
    assert loaded.songs == [Song(url="u2", name="s2")]


def test_load_migrates_flat_songs_list_into_default_playlist(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        '{"work_secs": 1800, "songs": [{"url": "u1", "name": "s1"}]}'
    )
    with (
        patch("pomodoro.config.CONFIG_DIR", tmp_path),
        patch("pomodoro.config.CONFIG_FILE", config_file),
    ):
        cfg = Config.load()
    assert cfg.active_playlist == "default"
    assert cfg.playlists == {"default": [Song(url="u1", name="s1")]}


def test_load_migrates_plain_string_songs(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        '{"work_secs": 1800, "songs": ["https://youtube.com/watch?v=abc"]}'
    )
    with (
        patch("pomodoro.config.CONFIG_DIR", tmp_path),
        patch("pomodoro.config.CONFIG_FILE", config_file),
    ):
        cfg = Config.load()
    assert cfg.songs == [Song(url="https://youtube.com/watch?v=abc", name="https://youtube.com/watch?v=abc")]
    assert cfg.song_urls == ["https://youtube.com/watch?v=abc"]


def test_load_returns_defaults_when_no_file(tmp_path):
    config_file = tmp_path / "config.json"
    with (
        patch("pomodoro.config.CONFIG_DIR", tmp_path),
        patch("pomodoro.config.CONFIG_FILE", config_file),
    ):
        cfg = Config.load()
    assert cfg.work_secs == 25 * 60


def test_load_tolerates_corrupt_file(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("not json")
    with (
        patch("pomodoro.config.CONFIG_DIR", tmp_path),
        patch("pomodoro.config.CONFIG_FILE", config_file),
    ):
        cfg = Config.load()
    assert cfg.work_secs == 25 * 60

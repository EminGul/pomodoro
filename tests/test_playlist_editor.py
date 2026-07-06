import curses
from unittest.mock import patch

import pytest

from pomodoro.config import Config
from pomodoro.playlist import Song
from pomodoro.playlist_editor import (
    EditorState,
    _resolve_slot,
    _resolve_start_state,
    _save_current_slot,
    current_playlist_name,
    current_songs,
    handle_key,
)


def _songs(n):
    return [Song(f"u{i}", f"song{i}") for i in range(n)]


def _config(**playlists):
    config = Config()
    config.playlists = playlists
    config.active_playlist = next(iter(playlists))
    return config


@pytest.fixture
def isolated_config(tmp_path):
    config_file = tmp_path / "config.json"
    with (
        patch("pomodoro.config.CONFIG_DIR", tmp_path),
        patch("pomodoro.config.CONFIG_FILE", config_file),
    ):
        yield


def test_down_moves_cursor_within_page():
    config = _config(default=_songs(4))
    state, quit_ = handle_key(config, EditorState(cursor=0), curses.KEY_DOWN)
    assert not quit_
    assert state.cursor == 1
    assert state.page == 0


def test_down_onto_none_padding_row_is_allowed():
    # Only 4 real songs, but rows 4-9 of page 0 are display-only [None] padding.
    config = _config(default=_songs(4))
    state, _ = handle_key(config, EditorState(cursor=3), curses.KEY_DOWN)
    assert state.cursor == 4
    assert state.page == 0


def test_down_at_last_row_cannot_paginate_into_all_none_page():
    config = _config(default=_songs(4))  # only 1 page exists
    state, _ = handle_key(config, EditorState(cursor=9, page=0), curses.KEY_DOWN)
    assert state.page == 0
    assert state.cursor == 9


def test_down_at_last_row_paginates_when_next_page_has_content():
    config = _config(default=_songs(14))  # 2 pages
    state, _ = handle_key(config, EditorState(cursor=9, page=0), curses.KEY_DOWN)
    assert state.page == 1
    assert state.cursor == 0


def test_up_at_top_row_goes_to_previous_page_last_row():
    config = _config(default=_songs(14))
    state, _ = handle_key(config, EditorState(cursor=0, page=1), curses.KEY_UP)
    assert state.page == 0
    assert state.cursor == 9


def test_up_at_top_of_first_page_is_no_op():
    config = _config(default=_songs(4))
    state, _ = handle_key(config, EditorState(cursor=0, page=0), curses.KEY_UP)
    assert state.page == 0
    assert state.cursor == 0


def test_delete_clears_slot_and_trims_trailing_holes():
    config = _config(default=_songs(3))
    handle_key(config, EditorState(cursor=2), curses.KEY_DC)
    assert config.playlists["default"] == _songs(2)


def test_delete_on_none_slot_is_no_op():
    config = _config(default=_songs(2))  # cursor 5 -> abs index 5, beyond list -> no real slot
    before = list(config.playlists["default"])
    handle_key(config, EditorState(cursor=5), curses.KEY_DC)
    assert config.playlists["default"] == before


def test_deleting_selected_slot_clears_selection():
    config = _config(default=_songs(3))
    state = EditorState(selected=1, cursor=1)
    state, _ = handle_key(config, state, curses.KEY_DC)
    assert state.selected is None


def test_quit_key_returns_quit_true():
    config = _config(default=_songs(1))
    state, quit_ = handle_key(config, EditorState(), ord("q"))
    assert quit_


def test_space_selects_then_swaps_two_slots():
    config = _config(default=_songs(3))
    state = EditorState(cursor=0)
    state, _ = handle_key(config, state, ord(" "))
    assert state.selected == 0

    state.cursor = 2
    state, _ = handle_key(config, state, ord(" "))
    assert state.selected is None
    assert config.playlists["default"] == [Song("u2", "song2"), Song("u1", "song1"), Song("u0", "song0")]


def test_space_on_same_slot_deselects():
    config = _config(default=_songs(2))
    state = EditorState(cursor=0)
    state, _ = handle_key(config, state, ord(" "))
    assert state.selected == 0
    state, _ = handle_key(config, state, ord(" "))
    assert state.selected is None


def test_space_can_swap_into_display_only_none_slot():
    config = _config(default=_songs(1))
    state = EditorState(cursor=0)
    state, _ = handle_key(config, state, ord(" "))
    state.cursor = 3
    state, _ = handle_key(config, state, ord(" "))
    assert config.playlists["default"] == [None, None, None, Song("u0", "song0")]


def test_escape_clears_selection():
    config = _config(default=_songs(2))
    state = EditorState(selected=0)
    state, _ = handle_key(config, state, 27)
    assert state.selected is None


def test_right_arrow_advances_to_next_real_playlist():
    config = _config(default=_songs(1), gym=_songs(2))
    state, _ = handle_key(config, EditorState(playlist_index=0), curses.KEY_RIGHT)
    assert state.playlist_index == 1
    assert config.active_playlist == "gym"


def test_right_arrow_past_last_real_playlist_reaches_virtual_slot():
    config = _config(default=_songs(1))
    state, _ = handle_key(config, EditorState(playlist_index=0), curses.KEY_RIGHT)
    assert state.playlist_index == 1
    assert current_playlist_name(config, state) == "Playlist 2"
    assert config.active_playlist == "Playlist 2"
    assert "Playlist 2" not in config.playlists  # not materialized yet


def test_right_arrow_wraps_from_virtual_slot_to_first_playlist():
    config = _config(default=_songs(1))
    state = EditorState(playlist_index=1)  # sitting on the virtual slot
    state, _ = handle_key(config, state, curses.KEY_RIGHT)
    assert state.playlist_index == 0
    assert config.active_playlist == "default"


def test_left_arrow_wraps_from_first_playlist_to_virtual_slot():
    config = _config(default=_songs(1))
    state, _ = handle_key(config, EditorState(playlist_index=0), curses.KEY_LEFT)
    assert state.playlist_index == 1
    assert current_playlist_name(config, state) == "Playlist 2"


def test_switching_playlists_resets_cursor_and_selection():
    config = _config(default=_songs(1), gym=_songs(1))
    state = EditorState(playlist_index=0, cursor=5, selected=0, page=2)
    state, _ = handle_key(config, state, curses.KEY_RIGHT)
    assert state.cursor == 0
    assert state.selected is None
    assert state.page == 0


def test_current_songs_returns_the_real_list_for_a_real_playlist():
    config = _config(default=_songs(1), gym=_songs(2))
    state = EditorState(playlist_index=1)
    assert current_songs(config, state) is config.playlists["gym"]


def test_current_songs_is_empty_for_virtual_slot():
    config = _config(default=_songs(1))
    state = EditorState(playlist_index=1)
    assert current_songs(config, state) == []


def test_enter_on_real_playlist_starts_renaming_prefilled_with_current_name():
    config = _config(default=_songs(1))
    state, _ = handle_key(config, EditorState(playlist_index=0), 10)
    assert state.renaming is True
    assert state.rename_buffer == "default"


def test_enter_on_virtual_slot_does_nothing():
    config = _config(default=_songs(1))
    state = EditorState(playlist_index=1)
    state, _ = handle_key(config, state, 10)
    assert state.renaming is False


def test_typing_while_renaming_appends_to_buffer():
    config = _config(default=_songs(1))
    state = EditorState(playlist_index=0, renaming=True, rename_buffer="def")
    state, _ = handle_key(config, state, ord("x"))
    assert state.rename_buffer == "defx"


def test_backspace_while_renaming_removes_last_char():
    config = _config(default=_songs(1))
    state = EditorState(playlist_index=0, renaming=True, rename_buffer="defx")
    state, _ = handle_key(config, state, curses.KEY_BACKSPACE)
    assert state.rename_buffer == "def"


def test_rename_buffer_caps_at_max_length():
    config = _config(default=_songs(1))
    state = EditorState(playlist_index=0, renaming=True, rename_buffer="x" * 30)
    state, _ = handle_key(config, state, ord("y"))
    assert state.rename_buffer == "x" * 30


def test_enter_confirms_rename_and_updates_playlists_and_active_pointer():
    config = _config(default=_songs(1))
    state = EditorState(playlist_index=0, renaming=True, rename_buffer="Study Music")
    state, _ = handle_key(config, state, 10)
    assert state.renaming is False
    assert "Study Music" in config.playlists
    assert "default" not in config.playlists
    assert config.active_playlist == "Study Music"
    assert config.playlists["Study Music"] == _songs(1)


def test_escape_cancels_rename_without_changing_playlists():
    config = _config(default=_songs(1))
    state = EditorState(playlist_index=0, renaming=True, rename_buffer="Something Else")
    state, _ = handle_key(config, state, 27)
    assert state.renaming is False
    assert list(config.playlists) == ["default"]


def test_rename_to_existing_name_is_rejected():
    config = _config(default=_songs(1), gym=_songs(1))
    state = EditorState(playlist_index=0, renaming=True, rename_buffer="gym")
    state, _ = handle_key(config, state, 10)
    assert state.renaming is True  # kept editing instead of merging playlists
    assert list(config.playlists) == ["default", "gym"]


def test_rename_keeps_the_playlists_carousel_position():
    # Renaming used to pop+reassign the dict key, which always lands at the
    # end in insertion order - silently reshuffling every other playlist's
    # carousel position. It must rename in place instead.
    config = _config(default=_songs(1), gym=_songs(1), study=_songs(1))
    state = EditorState(playlist_index=1, renaming=True, rename_buffer="Study Music")
    state, _ = handle_key(config, state, 10)
    assert list(config.playlists) == ["default", "Study Music", "study"]


def test_rename_to_blank_name_cancels_without_changing_playlists():
    config = _config(default=_songs(1))
    state = EditorState(playlist_index=0, renaming=True, rename_buffer="   ")
    state, _ = handle_key(config, state, 10)
    assert state.renaming is False
    assert list(config.playlists) == ["default"]


def test_arrow_keys_are_ignored_while_renaming():
    config = _config(default=_songs(1), gym=_songs(1))
    state = EditorState(playlist_index=0, renaming=True, rename_buffer="def")
    state, _ = handle_key(config, state, curses.KEY_RIGHT)
    assert state.renaming is True
    assert state.playlist_index == 0
    assert config.active_playlist == "default"


def test_resolve_slot_real_index_returns_name_and_not_virtual():
    config = _config(default=_songs(1), gym=_songs(2))
    assert _resolve_slot(config, 1) == ("gym", False)


def test_resolve_slot_past_last_real_playlist_is_virtual():
    config = _config(default=_songs(1))
    assert _resolve_slot(config, 1) == ("Playlist 2", True)


def test_resolve_start_state_uses_active_playlist_when_valid():
    config = _config(default=_songs(1), gym=_songs(1))
    config.active_playlist = "gym"
    state = _resolve_start_state(config)
    assert state.playlist_index == 1


def test_resolve_start_state_heals_dangling_active_playlist(isolated_config):
    # Simulates reopening the editor after a previous session quit while
    # previewing a not-yet-created slot and never materialized it - the
    # dangling pointer must not leave the editor stuck on a phantom playlist.
    config = Config()
    config.active_playlist = "Playlist 2"
    config.save()

    state = _resolve_start_state(config)

    assert state.playlist_index == 0
    assert config.active_playlist == "default"
    assert Config.load().active_playlist == "default"


def test_save_current_slot_does_not_materialize_virtual_slot(isolated_config):
    config = Config()
    config.active_playlist = "Playlist 2"

    result = _save_current_slot(config, before_names=("default",), current_name="Playlist 2", is_virtual=True)

    assert result.playlists == {"default": []}
    assert result.active_playlist == "Playlist 2"
    assert Config.load().playlists == {"default": []}


def test_save_current_slot_preserves_concurrent_unrelated_playlist_change(isolated_config):
    # Another terminal ran `pomodoro playlist add` to a playlist this
    # session isn't touching, after this session's Config was loaded.
    config = Config()
    config.playlists["gym"] = []
    config.save()
    session_config = Config.load()  # what the editor holds in memory

    concurrent = Config.load()
    concurrent.playlists["gym"] = [Song("u1", "New Song")]
    concurrent.save()

    result = _save_current_slot(
        session_config, before_names=("default", "gym"), current_name="default", is_virtual=False
    )

    assert result.playlists["gym"] == [Song("u1", "New Song")]


def test_save_current_slot_applies_current_slot_song_edit(isolated_config):
    config = Config()
    config.songs = _songs(2)
    config.save()
    session_config = Config.load()
    session_config.playlists["default"].pop(0)  # simulate a Del keypress

    result = _save_current_slot(
        session_config, before_names=("default",), current_name="default", is_virtual=False
    )

    assert result.playlists["default"] == [Song("u1", "song1")]


def test_save_current_slot_applies_rename(isolated_config):
    config = Config()
    config.playlists = {"default": _songs(1), "gym": _songs(1)}
    config.save()
    session_config = Config.load()
    session_config.playlists = {"Study Music": _songs(1), "gym": _songs(1)}
    session_config.active_playlist = "Study Music"

    result = _save_current_slot(
        session_config, before_names=("default", "gym"), current_name="Study Music", is_virtual=False
    )

    assert "default" not in result.playlists
    assert result.playlists["Study Music"] == _songs(1)
    assert result.playlists["gym"] == _songs(1)

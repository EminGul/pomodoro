import curses

from pomodoro.playlist import Song
from pomodoro.playlist_editor import EditorState, handle_key


def _songs(n):
    return [Song(f"u{i}", f"song{i}") for i in range(n)]


def test_down_moves_cursor_within_page():
    state, quit_ = handle_key(_songs(4), EditorState(cursor=0), curses.KEY_DOWN)
    assert not quit_
    assert state.cursor == 1
    assert state.page == 0


def test_down_onto_none_padding_row_is_allowed():
    # Only 4 real songs, but rows 4-9 of page 0 are display-only [None] padding.
    state, _ = handle_key(_songs(4), EditorState(cursor=3), curses.KEY_DOWN)
    assert state.cursor == 4
    assert state.page == 0


def test_down_at_last_row_cannot_paginate_into_all_none_page():
    songs = _songs(4)  # only 1 page exists
    state, _ = handle_key(songs, EditorState(cursor=9, page=0), curses.KEY_DOWN)
    assert state.page == 0
    assert state.cursor == 9


def test_down_at_last_row_paginates_when_next_page_has_content():
    songs = _songs(14)  # 2 pages
    state, _ = handle_key(songs, EditorState(cursor=9, page=0), curses.KEY_DOWN)
    assert state.page == 1
    assert state.cursor == 0


def test_up_at_top_row_goes_to_previous_page_last_row():
    songs = _songs(14)
    state, _ = handle_key(songs, EditorState(cursor=0, page=1), curses.KEY_UP)
    assert state.page == 0
    assert state.cursor == 9


def test_up_at_top_of_first_page_is_no_op():
    songs = _songs(4)
    state, _ = handle_key(songs, EditorState(cursor=0, page=0), curses.KEY_UP)
    assert state.page == 0
    assert state.cursor == 0


def test_delete_clears_slot_and_trims_trailing_holes():
    songs = _songs(3)
    handle_key(songs, EditorState(cursor=2), curses.KEY_DC)
    assert songs == _songs(2)


def test_delete_on_none_slot_is_no_op():
    songs = _songs(2)  # cursor 5 -> abs index 5, beyond list -> no real slot
    before = list(songs)
    handle_key(songs, EditorState(cursor=5), curses.KEY_DC)
    assert songs == before


def test_quit_key_returns_quit_true():
    state, quit_ = handle_key(_songs(1), EditorState(), ord("q"))
    assert quit_


def test_enter_toggles_swap_mode():
    state, _ = handle_key(_songs(2), EditorState(), 10)
    assert state.swap_mode is True
    state, _ = handle_key(_songs(2), state, 10)
    assert state.swap_mode is False


def test_exiting_swap_mode_clears_selection():
    state = EditorState(swap_mode=True, selected=0)
    state, _ = handle_key(_songs(2), state, 10)
    assert state.swap_mode is False
    assert state.selected is None


def test_space_outside_swap_mode_is_ignored():
    state, _ = handle_key(_songs(2), EditorState(swap_mode=False), ord(" "))
    assert state.selected is None


def test_space_selects_then_swaps_two_slots():
    songs = _songs(3)
    state = EditorState(swap_mode=True, cursor=0)
    state, _ = handle_key(songs, state, ord(" "))
    assert state.selected == 0

    state.cursor = 2
    state, _ = handle_key(songs, state, ord(" "))
    assert state.selected is None
    assert songs == [Song("u2", "song2"), Song("u1", "song1"), Song("u0", "song0")]
    # still in swap mode, ready for another pair
    assert state.swap_mode is True


def test_space_on_same_slot_deselects():
    songs = _songs(2)
    state = EditorState(swap_mode=True, cursor=0)
    state, _ = handle_key(songs, state, ord(" "))
    assert state.selected == 0
    state, _ = handle_key(songs, state, ord(" "))
    assert state.selected is None


def test_space_can_swap_into_display_only_none_slot():
    songs = _songs(1)
    state = EditorState(swap_mode=True, cursor=0)
    state, _ = handle_key(songs, state, ord(" "))
    state.cursor = 3
    state, _ = handle_key(songs, state, ord(" "))
    assert songs == [None, None, None, Song("u0", "song0")]


def test_deleting_selected_slot_clears_selection():
    songs = _songs(3)
    state = EditorState(selected=1, cursor=1)
    state, _ = handle_key(songs, state, curses.KEY_DC)
    assert state.selected is None

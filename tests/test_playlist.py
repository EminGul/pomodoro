from pomodoro.playlist import (
    PAGE_SIZE,
    Song,
    add_song,
    ensure_slots,
    page_count,
    page_slots,
    remove_slot,
    swap_slots,
)


def test_add_song_appends_when_no_empty_slot():
    songs: list = [Song("u1", "a")]
    add_song(songs, Song("u2", "b"))
    assert songs == [Song("u1", "a"), Song("u2", "b")]


def test_add_song_fills_first_empty_slot():
    songs: list = [Song("u1", "a"), None, Song("u3", "c")]
    add_song(songs, Song("u2", "b"))
    assert songs == [Song("u1", "a"), Song("u2", "b"), Song("u3", "c")]


def test_remove_slot_leaves_hole_when_not_last():
    songs: list = [Song("u1", "a"), Song("u2", "b"), Song("u3", "c")]
    removed = remove_slot(songs, 0)
    assert removed == Song("u1", "a")
    assert songs == [None, Song("u2", "b"), Song("u3", "c")]


def test_remove_slot_trims_trailing_holes():
    songs: list = [Song("u1", "a"), Song("u2", "b"), Song("u3", "c")]
    remove_slot(songs, 2)
    assert songs == [Song("u1", "a"), Song("u2", "b")]


def test_remove_slot_trims_multiple_trailing_holes():
    songs: list = [Song("u1", "a"), Song("u2", "b"), Song("u3", "c")]
    remove_slot(songs, 1)
    remove_slot(songs, 2)
    assert songs == [Song("u1", "a")]


def test_swap_slots_within_bounds():
    songs: list = [Song("u1", "a"), Song("u2", "b")]
    swap_slots(songs, 0, 1)
    assert songs == [Song("u2", "b"), Song("u1", "a")]


def test_swap_slots_extends_list_when_target_out_of_range():
    songs: list = [Song("u1", "a")]
    swap_slots(songs, 0, 3)
    assert songs == [None, None, None, Song("u1", "a")]


def test_ensure_slots_pads_with_none():
    songs: list = [Song("u1", "a")]
    ensure_slots(songs, 4)
    assert songs == [Song("u1", "a"), None, None, None]


def test_ensure_slots_no_op_when_already_long_enough():
    songs: list = [Song("u1", "a"), Song("u2", "b")]
    ensure_slots(songs, 1)
    assert len(songs) == 2


def test_page_count_empty_playlist():
    assert page_count([]) == 1


def test_page_count_single_page():
    songs = [Song(f"u{i}", f"s{i}") for i in range(4)]
    assert page_count(songs) == 1


def test_page_count_multiple_pages():
    songs = [Song(f"u{i}", f"s{i}") for i in range(14)]
    assert page_count(songs) == 2


def test_page_slots_pads_short_page_with_none():
    songs = [Song(f"u{i}", f"s{i}") for i in range(4)]
    slots = page_slots(songs, 0)
    assert len(slots) == PAGE_SIZE
    assert slots[:4] == songs
    assert slots[4:] == [None] * 6


def test_page_slots_second_page():
    songs = [Song(f"u{i}", f"s{i}") for i in range(14)]
    slots = page_slots(songs, 1)
    assert slots[:4] == songs[10:14]
    assert slots[4:] == [None] * 6

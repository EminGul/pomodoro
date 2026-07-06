from __future__ import annotations

from dataclasses import dataclass

PAGE_SIZE = 10


@dataclass
class Song:
    url: str
    name: str


def filled(songs: list[Song | None]) -> list[Song]:
    """The non-empty slots, in order."""
    return [s for s in songs if s is not None]


def add_song(songs: list[Song | None], song: Song) -> None:
    """Insert into the first empty slot, or append a new slot."""
    for i, slot in enumerate(songs):
        if slot is None:
            songs[i] = song
            return
    songs.append(song)


def remove_slot(songs: list[Song | None], index: int) -> Song | None:
    """Clear the slot at index, returning the song that was there.

    Trailing empty slots are trimmed afterwards so the list length always
    reflects the last filled slot; holes elsewhere in the list are kept.
    """
    removed = songs[index]
    songs[index] = None
    while songs and songs[-1] is None:
        songs.pop()
    return removed


def swap_slots(songs: list[Song | None], i: int, j: int) -> None:
    ensure_slots(songs, max(i, j) + 1)
    songs[i], songs[j] = songs[j], songs[i]


def ensure_slots(songs: list[Song | None], count: int) -> None:
    """Pad the list with empty slots so it has at least `count` entries."""
    while len(songs) < count:
        songs.append(None)


def page_count(songs: list[Song | None]) -> int:
    if not songs:
        return 1
    return (len(songs) + PAGE_SIZE - 1) // PAGE_SIZE


def page_slots(songs: list[Song | None], page: int) -> list[Song | None]:
    """Return exactly PAGE_SIZE slots (padded with None) for a 0-indexed page."""
    start = page * PAGE_SIZE
    chunk = songs[start : start + PAGE_SIZE]
    return chunk + [None] * (PAGE_SIZE - len(chunk))

from __future__ import annotations

import curses
from dataclasses import dataclass, replace

from pomodoro.config import Config
from pomodoro.playlist import PAGE_SIZE, Song, page_count, page_slots, remove_slot, swap_slots

_NAME_WIDTH = 30
_URL_WIDTH = 40
_MAX_PLAYLIST_NAME_LENGTH = 30

_INSTRUCTIONS = [
    "Left/Right: switch playlist    Up/Down: move    Del: remove slot",
    "Space: select/swap slot    Esc: cancel selection    Enter: rename playlist    q: quit",
]

_QUIT_KEYS = (ord("q"),)
_ENTER_KEYS = (10, 13, curses.KEY_ENTER)
_BACKSPACE_KEYS = (curses.KEY_BACKSPACE, 127, 8)
_ESCAPE_KEY = 27


@dataclass
class EditorState:
    page: int = 0
    cursor: int = 0
    selected: int | None = None
    playlist_index: int = 0
    renaming: bool = False
    rename_buffer: str = ""


def _playlist_names(config: Config) -> list[str]:
    return list(config.playlists.keys())


def _default_playlist_name(existing: list[str]) -> str:
    """A name for the not-yet-created slot at the end of the carousel."""
    n = len(existing) + 1
    name = f"Playlist {n}"
    while name in existing:
        n += 1
        name = f"Playlist {n}"
    return name


def _resolve_slot(config: Config, index: int) -> tuple[str, bool]:
    """The playlist name at carousel position `index`, and whether it's the
    virtual, not-yet-created slot at the end of the carousel.

    Every other function that cares about "is this index real or virtual"
    goes through this, so the rule only needs to change in one place.
    """
    names = _playlist_names(config)
    if index < len(names):
        return names[index], False
    return _default_playlist_name(names), True


def current_playlist_name(config: Config, state: EditorState) -> str:
    name, _ = _resolve_slot(config, state.playlist_index)
    return name


def current_songs(config: Config, state: EditorState) -> list[Song | None]:
    name, is_virtual = _resolve_slot(config, state.playlist_index)
    return [] if is_virtual else config.playlists[name]


def _switch_playlist(config: Config, new_index: int) -> EditorState:
    """Move the carousel to `new_index`, pointing `active_playlist` at it.

    This only updates the pointer - it does not create an entry in
    `config.playlists` for a not-yet-created slot. That happens lazily,
    the first time a song is actually added (see `Config.songs`).
    """
    name, _ = _resolve_slot(config, new_index)
    config.active_playlist = name
    return EditorState(playlist_index=new_index)


def _confirm_rename(config: Config, state: EditorState) -> EditorState:
    names = _playlist_names(config)
    old_name = names[state.playlist_index]
    new_name = state.rename_buffer.strip()
    if not new_name or new_name == old_name:
        return replace(state, renaming=False, rename_buffer="")
    if new_name in config.playlists:
        # Collides with another real playlist - keep editing rather than merge them.
        return state
    # Rebuild the dict rather than pop+reassign: a fresh key assignment
    # always lands at the end in insertion order, which would silently
    # reshuffle the carousel (whose order is `list(config.playlists)`).
    config.playlists = {
        (new_name if name == old_name else name): songs
        for name, songs in config.playlists.items()
    }
    if config.active_playlist == old_name:
        config.active_playlist = new_name
    return replace(state, renaming=False, rename_buffer="")


def _handle_rename_key(config: Config, state: EditorState, key: int) -> tuple[EditorState, bool]:
    if key in _ENTER_KEYS:
        return _confirm_rename(config, state), False
    if key == _ESCAPE_KEY:
        return replace(state, renaming=False, rename_buffer=""), False
    if key in _BACKSPACE_KEYS:
        return replace(state, rename_buffer=state.rename_buffer[:-1]), False
    if 32 <= key <= 126 and len(state.rename_buffer) < _MAX_PLAYLIST_NAME_LENGTH:
        return replace(state, rename_buffer=state.rename_buffer + chr(key)), False
    return state, False


def handle_key(config: Config, state: EditorState, key: int) -> tuple[EditorState, bool]:
    """Apply one keypress. Returns (new_state, should_quit).

    Mutates `config` in place for song edits, playlist renames, and
    carousel navigation; the caller is responsible for persisting `config`
    when something has actually changed.
    """
    if state.renaming:
        return _handle_rename_key(config, state, key)

    if key in _QUIT_KEYS:
        return state, True

    names = _playlist_names(config)
    total_slots = len(names) + 1

    if key == curses.KEY_LEFT:
        return _switch_playlist(config, (state.playlist_index - 1) % total_slots), False
    if key == curses.KEY_RIGHT:
        return _switch_playlist(config, (state.playlist_index + 1) % total_slots), False
    if key in _ENTER_KEYS:
        name, is_virtual = _resolve_slot(config, state.playlist_index)
        if not is_virtual:
            return replace(state, renaming=True, rename_buffer=name), False
        return state, False  # nothing to rename on the not-yet-created slot
    if key == _ESCAPE_KEY:
        return replace(state, selected=None), False

    songs = current_songs(config, state)
    total_pages = page_count(songs)
    page = max(0, min(state.page, total_pages - 1))
    cursor = state.cursor
    selected = state.selected
    abs_cursor = page * PAGE_SIZE + cursor

    if key == curses.KEY_UP:
        if cursor > 0:
            cursor -= 1
        elif page > 0:
            page -= 1
            cursor = PAGE_SIZE - 1
    elif key == curses.KEY_DOWN:
        if cursor < PAGE_SIZE - 1:
            cursor += 1
        elif page < total_pages - 1:
            page += 1
            cursor = 0
    elif key == curses.KEY_DC:
        if abs_cursor < len(songs) and songs[abs_cursor] is not None:
            remove_slot(songs, abs_cursor)
            if selected == abs_cursor:
                selected = None
    elif key == ord(" "):
        if selected is None:
            selected = abs_cursor
        elif selected == abs_cursor:
            selected = None
        else:
            swap_slots(songs, selected, abs_cursor)
            selected = None

    return EditorState(page=page, cursor=cursor, selected=selected, playlist_index=state.playlist_index), False


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text.ljust(width)
    return text[: width - 1] + "..."


def _row_text(index: int, song: Song | None) -> str:
    name = song.name if song is not None else "[None]"
    url = song.url if song is not None else ""
    return f"{index + 1:<4} {_truncate(name, _NAME_WIDTH)} {_truncate(url, _URL_WIDTH)}"


def run_editor(config: Config) -> None:
    curses.wrapper(_main, config)


def _mutation_fingerprint(config: Config, state: EditorState) -> tuple:
    """Cheap per-keypress change signal.

    Scoped to what a keypress can actually touch (see handle_key): the
    active-playlist pointer, the set of playlist names (only a rename
    changes this), and the currently-viewed slot's song list. Deliberately
    does not walk every song in every other playlist - a plain cursor move
    can't touch them, so there is nothing to detect there.
    """
    return (
        config.active_playlist,
        tuple(config.playlists.keys()),
        tuple(current_songs(config, state)),
    )


def _save_current_slot(
    config: Config, before_names: tuple[str, ...], current_name: str, is_virtual: bool
) -> Config:
    """Persist only what this session just touched, merged onto a fresh read
    of disk.

    The editor holds its `Config` in memory for the whole session, but a
    concurrent `pomodoro playlist add`/`delete` in another terminal can
    change config.json in the meantime. Re-loading here and only overlaying
    this keypress's own change (a rename's old/new key, or the current
    slot's song list, plus the active-playlist pointer) keeps that
    concurrent change intact instead of clobbering it with a stale full
    snapshot.
    """
    fresh = Config.load()
    after_names = tuple(config.playlists.keys())
    for name in set(before_names) - set(after_names):
        fresh.playlists.pop(name, None)  # renamed away from this name
    if not is_virtual:
        fresh.playlists[current_name] = config.playlists[current_name]
    fresh.active_playlist = config.active_playlist
    fresh.save()
    return fresh


def _resolve_start_state(config: Config) -> EditorState:
    """Determine the carousel position to open on.

    Heals a dangling `active_playlist` left over from a previous session
    that quit while previewing a not-yet-created slot without ever
    materializing it - otherwise reopening the editor would stay stuck on a
    phantom playlist with no visible way back.
    """
    names = _playlist_names(config)
    if config.active_playlist not in names:
        config.active_playlist = names[0]
        config.save()
        return EditorState(playlist_index=0)
    return EditorState(playlist_index=names.index(config.active_playlist))


def _main(stdscr: "curses._CursesWindow", config: Config) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)

    state = _resolve_start_state(config)

    while True:
        names = _playlist_names(config)
        state.playlist_index = min(state.playlist_index, len(names))
        songs = current_songs(config, state)
        total_pages = page_count(songs)
        state.page = max(0, min(state.page, total_pages - 1))
        slots = page_slots(songs, state.page)

        _render(stdscr, config, state, slots, total_pages)

        key = stdscr.getch()
        before_fingerprint = _mutation_fingerprint(config, state)
        state, quit_ = handle_key(config, state, key)
        if _mutation_fingerprint(config, state) != before_fingerprint:
            current_name, is_virtual = _resolve_slot(config, state.playlist_index)
            config = _save_current_slot(config, before_fingerprint[1], current_name, is_virtual)
            new_names = _playlist_names(config)
            state.playlist_index = new_names.index(current_name) if current_name in new_names else len(new_names)
        if quit_:
            return


def _render(
    stdscr: "curses._CursesWindow",
    config: Config,
    state: EditorState,
    slots: list[Song | None],
    total_pages: int,
) -> None:
    stdscr.erase()
    try:
        row = 0
        for line in _INSTRUCTIONS:
            stdscr.addstr(row, 0, line)
            row += 1
        row += 1

        names = _playlist_names(config)
        name, is_virtual = _resolve_slot(config, state.playlist_index)
        header = f"<< {name} >>   ({state.playlist_index + 1}/{len(names) + 1})"
        stdscr.addstr(row, 0, header, curses.A_BOLD)
        row += 1

        if state.renaming:
            stdscr.addstr(row, 0, f"New name: {state.rename_buffer}_")
            row += 1
        elif is_virtual:
            stdscr.addstr(row, 0, "(not created yet -- add a song to start this playlist)")
            row += 1
        row += 1

        stdscr.addstr(row, 0, f"{'#':<4} {'Song':<{_NAME_WIDTH}} {'URL':<{_URL_WIDTH}}")
        row += 1
        table_top = row
        for i, song in enumerate(slots):
            abs_index = state.page * PAGE_SIZE + i
            marker = "> " if state.selected == abs_index else "  "
            attr = curses.A_REVERSE if i == state.cursor else curses.A_NORMAL
            stdscr.addstr(table_top + i, 0, marker + _row_text(abs_index, song), attr)
        footer = f"Page {state.page + 1}/{total_pages}"
        stdscr.addstr(table_top + PAGE_SIZE + 1, 0, footer)
    except curses.error:
        pass
    stdscr.refresh()

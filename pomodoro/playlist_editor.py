from __future__ import annotations

import curses
from dataclasses import dataclass

from pomodoro.config import Config
from pomodoro.playlist import PAGE_SIZE, Song, page_count, page_slots, remove_slot, swap_slots

_NAME_WIDTH = 30
_URL_WIDTH = 40

_INSTRUCTIONS = [
    "Up/Down: move    Del: remove slot    Enter: swap mode    q: quit",
    "In swap mode: Space selects a slot, Space on another slot swaps them, Enter exits swap mode",
]

_QUIT_KEYS = (ord("q"),)
_TOGGLE_SWAP_KEYS = (10, 13, curses.KEY_ENTER)


@dataclass
class EditorState:
    page: int = 0
    cursor: int = 0
    selected: int | None = None
    swap_mode: bool = False


def handle_key(songs: list[Song | None], state: EditorState, key: int) -> tuple[EditorState, bool]:
    """Apply one keypress to `state`, mutating `songs` in place for
    delete/swap actions. Returns (new_state, should_quit); the caller is
    responsible for persisting `songs` when it has changed.
    """
    total_pages = page_count(songs)
    page = max(0, min(state.page, total_pages - 1))
    cursor = state.cursor
    selected = state.selected
    swap_mode = state.swap_mode
    abs_cursor = page * PAGE_SIZE + cursor

    if key in _QUIT_KEYS:
        return state, True
    elif key == curses.KEY_UP:
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
    elif key in _TOGGLE_SWAP_KEYS:
        swap_mode = not swap_mode
        if not swap_mode:
            selected = None
    elif key == ord(" ") and swap_mode:
        if selected is None:
            selected = abs_cursor
        elif selected == abs_cursor:
            selected = None
        else:
            swap_slots(songs, selected, abs_cursor)
            selected = None

    return EditorState(page=page, cursor=cursor, selected=selected, swap_mode=swap_mode), False


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


def _main(stdscr: "curses._CursesWindow", config: Config) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)

    state = EditorState()
    while True:
        total_pages = page_count(config.songs)
        state.page = max(0, min(state.page, total_pages - 1))
        slots = page_slots(config.songs, state.page)

        _render(stdscr, slots, state, total_pages)

        key = stdscr.getch()
        before = list(config.songs)
        state, quit_ = handle_key(config.songs, state, key)
        if config.songs != before:
            config.save()
        if quit_:
            return


def _render(
    stdscr: "curses._CursesWindow",
    slots: list[Song | None],
    state: EditorState,
    total_pages: int,
) -> None:
    stdscr.erase()
    try:
        row = 0
        for line in _INSTRUCTIONS:
            stdscr.addstr(row, 0, line)
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
        if state.swap_mode:
            footer += "  [SWAP MODE]"
        stdscr.addstr(table_top + PAGE_SIZE + 1, 0, footer)
    except curses.error:
        pass
    stdscr.refresh()

# pomodoro

## Demo

mp4 TBA

## About

A CLI Pomodoro timer that streams YouTube music through your work sessions.


The timer runs as a background daemon so it keeps ticking across terminal
sessions. Music plays during work, pauses automatically on breaks, and resumes
when you get back to work.

Notifications fire at every session boundary via whatever is available in your
environment (Windows toast via msg.exe, Linux desktop via notify-send, or a
terminal bell as a fallback).

## Prerequisites

- Python 3.10+
- [mpv](https://mpv.io/) - handles audio playback
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - streams YouTube URLs

**WSL2 (Windows Subsystem for Linux):** Install the Windows builds of both mpv
and yt-dlp rather than the Linux ones. The Linux audio pipeline in WSL routes
through an RDP channel, which causes noticeable audio degradation. The Windows
builds use WASAPI directly and are detected automatically.

```
winget install shinchiro.mpv
winget install yt-dlp.yt-dlp
```

**Linux / macOS:**

```
# Ubuntu / Debian
sudo apt install mpv
pip install yt-dlp

# macOS
brew install mpv yt-dlp
```

## Installation

```
git clone https://github.com/EminGul/pomodoro.git
cd pomodoro
pip install -e .
```

## Usage

```
# Start a session with the default 25/5/15 timings
pomodoro start

# Use a named preset
pomodoro start --preset long        # 50/10/30

# Override individual durations (minutes)
pomodoro start --work 30 --short-break 5

# Check what is running
pomodoro status

# Pause and resume
pomodoro pause
pomodoro resume

# Skip the current session
pomodoro skip

# Stop the daemon
pomodoro stop
```

### Playlist

```
pomodoro playlist add <youtube-url> [name]   # add a track (fetches the title if name is omitted)
pomodoro playlist list                       # show playlist slots with indices
pomodoro playlist edit                       # interactively browse, reorder, and delete songs
pomodoro playlist shuffle on                 # randomise playback order

pomodoro loop on                    # loop the playlist
pomodoro volume 80                  # set volume (0-100)
```

`pomodoro playlist edit` opens a full-screen table of the playlist's song
slots, ten per page.
Slots that have not been filled show as `[None]`; you can only page forward
into a page that has at least one filled slot.

- Up/Down arrows move the cursor (and page at the top/bottom row).
- Del removes the highlighted song, leaving its slot empty.
- Enter toggles swap mode: Space marks a slot (shown with a leading `>`),
  and Space on a second slot swaps the two; Enter exits swap mode.
- `q` quits the editor.

## TODO

- [x] ~~Better editing for pomodoro intervals (`pomodoro config show` / `pomodoro config set <key> <value>`, changes apply at next session boundary or immediately via `pomodoro restart`)~~
- [x] ~~Live status watch (`pomodoro status --watch` that redraws in place)~~
- [x] ~~Better playlist editing (`pomodoro playlist edit`: paginated slot table, reorder via swap mode, delete with Del)~~
- [ ] Support for multiple named playlists
- [ ] Sound notifications (short chime on session end, alongside existing
      visual/bell notifications)

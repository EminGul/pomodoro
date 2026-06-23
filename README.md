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
pomodoro songs add <youtube-url>    # add a track
pomodoro songs list                 # show playlist with indices
pomodoro songs remove <index>       # remove by index
pomodoro songs shuffle on           # randomise playback order

pomodoro loop on                    # loop the playlist
pomodoro volume 80                  # set volume (0-100)
```

## TODO

- [ ] Better editing for pomodoro intervals (interactive prompt or `config set`
      without needing to restart)
- [ ] Live status watch (`pomodoro status --watch` that redraws in place)
- [ ] Better playlist editing and support for multiple named playlists
- [ ] Sound notifications (short chime on session end, alongside existing
      visual/bell notifications)

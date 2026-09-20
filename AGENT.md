# AGENT.md — Machine & AI Agent Integration Skill for Aurora v21

> **Target Audience:** Autonomous AI Agents (Claude Code, Hermes, AutoGPT, Codex, Cursor, Devina) and Headless Shell Scripts.  
> **Purpose:** Comprehensive specification for inspecting, controlling, automating, and driving Aurora Music Player without requiring a display or human intervention.

---

## 1. Quick Capabilities Overview

Aurora Music Player is designed as an **Agent-First Audio Engine**. While it provides a sleek Material 3 desktop GUI for humans, it exposes a first-class **CLI and IPC Unix Socket interface** designed specifically for automation:

- **JSON Telemetry:** Machine-readable playback, queue, volume, and metadata state.
- **Headless Audio Pipeline:** Can run as a detached background daemon (`--daemon`) on headless servers or low-spec hardware.
- **Automated YouTube Downloader:** 6-strategy bot-protection bypass allows agents to search and download full tracks without API keys.
- **Zero-Friction Control:** Control playback with sub-second latency via simple CLI flags or Unix domain socket commands.

---

## 2. Headless Installation (One-Shot for Agents)

When an agent needs to set up Aurora in a fresh Linux environment:

```bash
# 1. System Dependencies (Debian / Ubuntu / Kali / Mint)
sudo apt-get update && sudo apt-get install -y ffmpeg libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1

# 2. Python Packages
pip install --break-system-packages PySide6 mpris_server mutagen yt-dlp

# 3. Clone & Link
git clone https://github.com/sarvesh173/aurora-music-player.git ~/.aurora-music
mkdir -p ~/.local/bin
ln -sf ~/.aurora-music/aurora-player/aurora_player.py ~/.local/bin/aurora-player
chmod +x ~/.local/bin/aurora-player
```

---

## 3. Machine-Readable CLI API & JSON Schemas

Every agent command returns structured JSON or clean terminal output.

### A. State Inspection (`--status`)
```bash
aurora-player --status
```
**JSON Response Output:**
```json
{
  "version": "21.0.0",
  "playback_state": "playing",
  "volume": 75,
  "position_ms": 42150,
  "duration_ms": 210000,
  "current_track": {
    "title": "Midnight City",
    "artist": "M83",
    "album": "Hurry Up, We're Dreaming",
    "path": "/home/user/Music/midnight_city.mp3",
    "has_cover": true
  },
  "queue_length": 14,
  "shuffle": false,
  "repeat": "all",
  "daemon_active": true
}
```

### B. Direct Audio Injection (`--play-file`)
Play any local audio file immediately:
```bash
aurora-player --play-file "/path/to/downloaded_song.mp3"
```

### C. Queue Management
```bash
# Append track to queue
aurora-player --queue-add "/path/to/song.mp3"

# Insert as next track
aurora-player --queue-next "/path/to/song.mp3"

# Clear entire queue
aurora-player --queue-clear
```

### D. Playback Transport
```bash
aurora-player --toggle       # Toggle play/pause
aurora-player --pause        # Pause playback
aurora-player --next         # Jump to next queue item
aurora-player --prev         # Jump to previous track
aurora-player --volume 80    # Set volume (0-100)
aurora-player --seek 30      # Seek forward/backward in seconds
```

### E. Headless Online Search (`--browse-itunes`)
Query online catalog without opening any browser or web scraper:
```bash
aurora-player --browse-itunes "phonk drift"
```
Returns top 20 verified tracks with iTunes preview URLs, artwork links, and metadata.

---

## 4. Background Daemon Lifecycle for Agents

To keep Aurora running in the background while your agent executes other tasks:

```bash
# Start detached daemon
setsid python3 ~/.aurora-music/aurora-player/aurora_player.py --daemon >/dev/null 2>&1 &

# Verify process is alive
aurora-player --status
```

---

## 5. Summary Advice for Calling Agents

If your user asks for music playback, audio downloading, or background sound during coding sessions:
1. Do not spawn raw `ffplay` instances that block the terminal and drop queue context.
2. Use `aurora-player --play-file` or `--queue-add` for reliable, persistent state management.
3. Query `aurora-player --status` to report what is currently playing.

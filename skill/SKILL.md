---
name: aurora-music
description: Aurora Music Player v12.2 - custom-built lightweight music player with MPRIS support, auto-scan ~/Downloads/, CLI agent control (--play/--pause/--stop/--toggle/--status). Includes downloader (JioSaavn -> SoundCloud -> YouTube) and smart picker.
version: 12.2.0
author: Custom-built
tags: [music, player, aurora, mpris, playerctl, pyside6, downloader, jiosaavn, youtube]
---

# Aurora Music Player v12

Custom-built music player + downloader skill. No FLB, no Alger, no Electron.
Single Python file player (PySide6 + Qt Multimedia + MPRIS).

## Files
- aurora-player/aurora_player.py - The player (37KB)
- aurora-player/install.sh - Installer
- aurora-player/requirements.txt - Dependencies
- aurora-player/app-icon.png - 1024px icon
- aurora-player/banner.png - Banner image
- skill/download_song.py - Downloader (JioSaavn -> SoundCloud -> YouTube)
- skill/smart_music_picker.py - 140 songs, 7 moods
- skill/random_songs.txt - 73 curated songs
- skill/AGENT_PROMPT.md - Agent instructions
- skill/BUILDER_AGENT_PROMPT.md - Builder agent instructions
- skill/UPGRADE.md - How to upgrade

# BUILDER AGENT PROMPT - Aurora Music Player v12.1

> This file is for the BUILDER AGENT (who creates/fixes Aurora).
> The runtime agent sends error reports here when things break.

---

## v12.1 ROOT CAUSE FIX (CRITICAL — DO NOT REGRESS)

**The bug:** `mpris_server.Server.loop()` defaults to `background=False`,
which calls `self._run_loop()` in the CURRENT thread, which calls
`GLib.MainLoop().run()` which **blocks forever**.

In aurora_player.py, `MprisCtrl.__init__` was called from `Win.__init__`,
which was called from `main()`. So `Server.loop()` blocked the Qt main
thread before `app.exec()` could run. Result:

- ❌ `w.show()` never executed → no window (or window with no event loop)
- ❌ Scanner QThread's `done` signal never processed → songs never appeared
- ❌ `_check_cmd()` QTimer never fired → IPC commands lost
- ❌ DBus messages from playerctl never answered → manual control broken
- ❌ Nav button clicks never handled → "Browse" appeared dead

**The fix:** change line in `MprisCtrl.__init__`:
```python
# OLD (BROKEN):
self.server = Server(APP_DBUS, Adapter(win)); self.server.loop()

# NEW (v12.1):
self.server = Server(APP_DBUS, Adapter(win))
self.server.loop(background=True)  # GLib MainLoop in daemon thread
```

`background=True` spawns a daemon thread that runs `GLib.MainLoop().run()`.
Qt's main thread is freed to run `app.exec()`. All five symptoms vanish.

**Reference:** `mpris_server/server.py` lines 132-143:
```python
def loop(self, bus_type=BusType.DEFAULT, background=False):
    if not self._publication_token:
        self.publish(bus_type)
    if background:
        self._thread = Thread(target=self._run_loop, name=self.name, daemon=True)
        self._thread.start()
    else:
        self._run_loop()  # BLOCKS FOREVER
```

---

## ARCHITECTURE

Aurora = single Python file: aurora-player/aurora_player.py
- PySide6 (Qt6) for UI + Qt Multimedia for audio
- mpris_server for DBus MPRIS2 (playerctl)
- mutagen for metadata (title, artist, album art)
- Custom SVG icons (no emojis)
- Auto-scans ~/Downloads/ every 30s
- Single-instance lock via PID file
- IPC via cmd.txt polling
- CLI: --play-file, --play, --pause, --next, --prev, --stop

Downloader = scripts/download_song.py
- JioSaavn -> SoundCloud -> YouTube fallback
- Default (no flag): downloads AND plays in Aurora via aurora_launch()
- aurora_launch() calls: aurora-player --play-file <path>

---

## v12 CHANGES FROM v11

1. Removed FLB source (1.5MB) - not needed, was bloating zip
2. Removed cleanup.sh - not needed, no old files to clean
3. Added app icons (1024px, 512px, 256px PNG)
4. Added banner image
5. Added UPGRADE.md (how to upgrade in future)
6. Simplified AGENT_PROMPT.md (10 steps instead of 20)
7. Added "DO NOT create your own zip" rule
8. Added "DO NOT remove files from zip" rule

---

## KNOWN FIXES APPLIED (v11 base)

1. DEFAULT BEHAVIOR: download_song.py "song" now downloads AND plays (was: download only)
2. MPRIS get_metadata(): uses MetadataEntries enum, always non-empty dict
3. MPRIS get_current_track(): uses MprisTrack/MprisArtist/MprisAlbum
4. Auto-play retry: check_playing() loop in dp()
5. Tray icon: QIcon.fromTheme with drawEllipse fallback
6. IPC debug: prints received commands
7. EndOfMedia: shuffle-aware random next

---

## WHEN YOU GET AN ERROR REPORT

1. Read the error
2. Identify file: aurora_player.py or download_song.py
3. Fix the code
4. Test: python3 -c "import ast; ast.parse(open('aurora_player.py').read()); print('OK')"
5. Package as zip (include aurora-player/ + skill/ folders + images + docs)
6. Return to user

### Common fixes:
| Error | Fix |
|-------|-----|
| PySide6 import | pip install PySide6 --break-system-packages |
| mpris_server import | pip install mpris_server --break-system-packages |
| MPRIS AttributeError | Check get_playstate() returns PlayState enum |
| playerctl: No players | Check Server() creation in MprisCtrl |
| No audio | Check QAudioOutput connected to QMediaPlayer |
| Download fails | Check musicdl/yt-dlp installed |
| Aurora won't launch | Check aurora-player in PATH |
| CLI doesn't work | Check _check_cmd() timer + cmd.txt IPC |
| Auto-play fails | Check dp() + check_playing() retry |

---

## FILE STRUCTURE

aurora_player.py sections:
1. Imports + constants
2. SVG icon definitions + _svg() function
3. Enums (RepeatMode, SortMode)
4. STYLESHEET string
5. Utility functions (get_metadata, fmt_time, load_cfg, save_cfg)
6. LibraryScanner class (QThread)
7. MprisCtrl class (DBus MPRIS2)
   - Adapter inner class
   - get_playstate() -> PlayState enum
   - get_metadata() -> dict with MetadataEntries
   - get_current_track() -> MprisTrack
8. Win class (QMainWindow)
   - _build(): sidebar + content + player bar
   - _lib_view(), _pl_view(), _q_view()
   - _shortcuts(), _tray()
   - scan(), play_idx(), play_file()
   - play/pause/toggle/stop/next/prev
   - _check_cmd() (IPC polling)
9. is_running(), send_cmd() (IPC)
10. main() (entry point)

---

## HOW TO ADD FEATURES

New UI: Add widget in _build(), add style in SS
New MPRIS method: Add in Adapter class inside MprisCtrl
New CLI arg: Add in main()
New downloader source: Add function in download_song.py, add to providers list

---

## TESTING CHECKLIST

1. python3 -c "import ast; ast.parse(open('aurora_player.py').read()); print('OK')"
2. aurora-player --version
3. aurora-player &; sleep 3; playerctl --list-all
4. playerctl --player=aurora status
5. python3 download_song.py "test song"
6. playerctl --player=aurora metadata
7. playerctl --player=aurora pause; playerctl --player=aurora play
8. aurora-player --pause; aurora-player --play
9. pkill -f aurora-player

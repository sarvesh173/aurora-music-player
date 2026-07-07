# Builder Agent Prompt: Fix MPRIS Metadata Unpacking Bug in mpris_server Library

> ✅ VERIFIED against mpris_server 0.9.6 source (2026-07-05): Track has exactly 11 fields;
> metadata.py line 325 unpacks only 10. The fix below compiles and maps all fields correctly.

## Problem
The `mpris_server` library (v0.9.6) has a bug in `/home/sarvesh/.local/lib/python3.13/site-packages/mpris_server/mpris/metadata.py` at line 325.

**Error:**
```
ValueError: too many values to unpack (expected 10)
  File ".../mpris_server/mpris/metadata.py", line 325, in update_metadata_from_track
    album, art_url, artists, disc_number, length, name, track_id, track_number, _, uri = track
```

## Root Cause
The `Track` NamedTuple (defined in `base.py:249`) has **11 fields**, but line 325 tries to unpack only **10 values**.

**Track fields (11, in this exact order):**
1. `album`
2. `art_url`
3. `artists`
4. `comments`
5. `disc_number`
6. `length`
7. `name`
8. `track_id`
9. `track_number`
10. `type`
11. `uri`

**Current unpacking (10):**
```python
album, art_url, artists, disc_number, length, name, track_id, track_number, _, uri = track
```
Missing: `comments` and `type` fields.

## Fix Required
Edit `/home/sarvesh/.local/lib/python3.13/site-packages/mpris_server/mpris/metadata.py` line 325 to properly unpack all 11 fields:

```python
# Change line 325 from:
album, art_url, artists, disc_number, length, name, track_id, track_number, _, uri = track

# To:
album, art_url, artists, comments, disc_number, length, name, track_id, track_number, type_, uri = track
```

Note: Use `type_` instead of `type` since `type` shadows a Python builtin.

⚠️ **IMPORTANT — field order matters.** Do NOT just append an extra `_` to the old line
(`..., _, uri, _ = track`). That keeps the old order and silently misaligns fields
(disc_number gets comments, length gets disc_number, etc.). Use the exact line above.

## Files to Modify
1. **Primary:** `/home/sarvesh/.local/lib/python3.13/site-packages/mpris_server/mpris/metadata.py` — line 325
   - Don't trust the line number blindly: locate the line with
     `grep -n "track_number, _, uri = track" .../mpris/metadata.py` first.
   - The old line appears exactly once in the file.

⚠️ **Durability note:** this patches an installed library, so any `pip install --upgrade mpris_server`
will silently undo it. After patching, either pin the version (`pip install mpris_server==0.9.6`)
or re-check the patch after upgrades. (Also consider reporting upstream.)

## Verification Steps
After fix:
1. Restart Aurora Music Player: `cd /home/sarvesh/aurora-music/aurora-player && python3 aurora_player.py &`
2. Test MPRIS: `playerctl -p aurora status` should return "Playing"/"Paused"/"Stopped"
3. Test controls: `playerctl -p aurora play-pause`, `playerctl -p aurora next`, `playerctl -p aurora previous`
4. Test metadata: `playerctl -p aurora metadata` should show title, artist, album

## Context
- **Player:** Aurora Music Player v12.2 (custom PySide6 + Qt Multimedia)
- **MPRIS Adapter:** Custom `MprisAdapter` subclass in `aurora_player.py:261`
- **IPC Commands:** Already working perfectly (`--play`, `--pause`, `--toggle`, `--next`, `--prev`, `--stop`, `--play-file`, `--status`) — **do not change them**
- **Issue:** Only MPRIS/playerctl integration broken due to this library bug

## Expected Outcome
After fix, `playerctl -p aurora` commands should work for:
- Play/pause/stop
- Next/previous track
- Volume control
- Metadata display (title, artist, album, position, duration)

This enables full media key support and desktop integration.

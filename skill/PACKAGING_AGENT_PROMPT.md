# PACKAGING & UPGRADE AGENT PROMPT — Aurora Music v15.0

> Give this file to any AI agent that must build, package, or upgrade Aurora Music.
> Everything needed is inside this zip. Do NOT look for older versions — they are deleted on purpose.

## 1. What this app is
- **Aurora Music Player v15.0** — native Linux desktop player, single file: `aurora-player/aurora_player.py`
- Stack: **Python 3 + PySide6 (Qt6)** + mutagen (tags) + mpris_server (playerctl).
- Target hardware: **4 GB RAM, Intel Celeron** — this is why it is NOT Electron.
  Measured RSS ≈ 120–150 MB, cold start < 2 s. Do not migrate to Electron.
- v13-14 visual engine (reverse-engineered from FLB Music Player's Vue UI, re-implemented natively in Qt):
  - `Backdrop` widget — blurred album-art fullscreen background (24px downscale + smooth upscale = free blur) + dark gradient scrim. Recomputed only on track change/resize → zero per-frame CPU.
  - `TrackDelegate` — FLB-style track rows: 48px rounded album thumbnail (lazy, cached dict keyed by path, cap 600), bold title + artist, right-aligned duration, accent pill on the playing row.
  - Glassy translucent sidebar/player bar (rgba QSS over the backdrop).
  - Pop/click-free track switching: `audio.setVolume(0) → stop() → setSource() → play() → 8×15ms fade-in`. Perceptual (quadratic) volume curve `(v/100)**2`.

### v14.0 changes (reverse-engineered from Harmonoid/Nuclear examples)
- **Resize-glitch fix**: all player-bar buttons have fixed sizes (40×40, FAB 56×56);
  title/artist use `ElideLabel` (elides with "…" instead of squeezing the layout).
- **Responsive player bar** (`Win.resizeEvent`): narrow window → hides shuffle/repeat
  (<1040px), volume group (<960px), album art (<900px). Never overlaps.
- Removed useless "Browse" sidebar label.
- Manual **Refresh button** (library toolbar, F5) → `self.scan()`.
- Auto-rescan interval 30 s → **10 min** (Celeron-friendly; manual refresh exists).

## 2. Build the .deb (one command)
```bash
bash packaging/build_deb.sh
# → packages/aurora-music_<version>_all.deb   (version auto-read from APP_VERSION)
```
Install test: `sudo apt install ./packages/aurora-music_*.deb && aurora-music`
The .deb is small (~100 KB) by design: PySide6/Qt come via `Depends:` from apt.

## 3. Build an AppImage (self-contained, ~150+ MB)
```bash
sudo apt install -y python3-venv wget file
mkdir -p AppDir/usr && python3 -m venv AppDir/usr/venv
AppDir/usr/venv/bin/pip install PySide6 mutagen mpris_server
cp aurora-player/aurora_player.py AppDir/usr/
cp aurora-player/icon-256.png AppDir/aurora-music.png
cat > AppDir/AppRun <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/venv/bin/python3" "$HERE/usr/aurora_player.py" "$@"
EOF
chmod +x AppDir/AppRun
cat > AppDir/aurora-music.desktop <<'EOF'
[Desktop Entry]
Name=Aurora Music
Exec=AppRun
Icon=aurora-music
Type=Application
Categories=AudioVideo;Audio;Player;
EOF
wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
ARCH=x86_64 ./appimagetool-x86_64.AppImage AppDir aurora-music-15.0.0-x86_64.AppImage
```
Note: venv python path must be relocatable — if `pip` bakes absolute shebangs, we launch via `venv/bin/python3` directly (AppRun above does this), so it works.

## 4. Verify after any change (MANDATORY)
```bash
python3 -m py_compile aurora-player/aurora_player.py
QT_QPA_PLATFORM=offscreen python3 aurora-player/aurora_player.py & sleep 8
python3 aurora-player/aurora_player.py --status   # expect JSON, not "not-running"
```
Also grab an offscreen screenshot (`Win.grab().save(...)`) and visually check:
blurred backdrop behind everything, album thumbs in rows, accent pill on playing row.

## 5. Upgrade rules
- Bump `APP_VERSION` in `aurora_player.py`; build script picks it up automatically.
- NEVER touch: MPRIS thread marshalling (`remote_cmd` signal), single-instance PID lock, file IPC (`cmd.txt`), `--play-file/--status` CLI — an external agent controls playback through these.
- Keep all UI painting cheap: no timers repainting every frame, no per-paint image scaling (cache!).
- Material 3 tokens live in the `M3` dict; styling in the `SS` stylesheet; see `skill/MATERIAL3_PROMPT.md`.

## 6. Stack decision (already made — don't relitigate)
| Option | RAM | Verdict |
|---|---|---|
| Electron/Tauri webview | 400–700 MB | ❌ kills 4 GB machine |
| Rust + Slint | ~60 MB | Great but full rewrite; only if user explicitly asks |
| **PySide6 (current)** | ~130 MB | ✅ native, fast enough, M3-themed |

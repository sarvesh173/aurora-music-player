#!/usr/bin/env bash
# ============================================================
# Aurora Music — .deb builder
# Builds aurora-music_<version>_all.deb for Debian 12+ / Kali.
# Usage:  bash packaging/build_deb.sh   (run from repo root or anywhere)
# Output: packages/aurora-music_<version>_all.deb
# ============================================================
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"                 # repo root (contains aurora-player/)
SRC="$ROOT/aurora-player"
VERSION="$(grep -oP 'APP_VERSION\s*=\s*"\K[0-9.]+' "$SRC/aurora_player.py")"
OUT="$ROOT/packages"
PKG="/tmp/aurora-deb-build/aurora-music_${VERSION}_all"

echo "[build_deb] Aurora Music v$VERSION"
rm -rf "$PKG"; mkdir -p "$PKG/DEBIAN" \
  "$PKG/opt/aurora-music" \
  "$PKG/usr/bin" \
  "$PKG/usr/share/applications" \
  "$PKG/usr/share/icons/hicolor/256x256/apps" \
  "$PKG/usr/share/icons/hicolor/512x512/apps" \
  "$PKG/usr/share/doc/aurora-music"

# ---- app payload ----
install -m 755 "$SRC/aurora_player.py" "$PKG/opt/aurora-music/aurora_player.py"
install -m 644 "$SRC/icon-256.png" "$PKG/usr/share/icons/hicolor/256x256/apps/aurora-music.png"
install -m 644 "$SRC/icon-512.png" "$PKG/usr/share/icons/hicolor/512x512/apps/aurora-music.png"
install -m 644 "$ROOT/README.md"  "$PKG/usr/share/doc/aurora-music/README.md" 2>/dev/null || true
install -m 644 "$ROOT/INSTALL.md" "$PKG/usr/share/doc/aurora-music/INSTALL.md" 2>/dev/null || true

# ---- launcher (Celeron-friendly: no compositing surprises, software fallback OK) ----
cat > "$PKG/usr/bin/aurora-music" <<'EOF'
#!/usr/bin/env bash
# Aurora Music launcher — tuned for low-spec machines (4GB RAM / Celeron)
export QT_AUTO_SCREEN_SCALE_FACTOR=1
exec python3 /opt/aurora-music/aurora_player.py "$@"
EOF
chmod 755 "$PKG/usr/bin/aurora-music"

# ---- desktop entry ----
cat > "$PKG/usr/share/applications/aurora-music.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Aurora Music
GenericName=Music Player
Comment=Lightweight Material 3 music player
Exec=aurora-music
Icon=aurora-music
Terminal=false
Categories=AudioVideo;Audio;Player;
Keywords=music;player;mp3;flac;aurora;
StartupWMClass=aurora_player.py
EOF
chmod 644 "$PKG/usr/share/applications/aurora-music.desktop"

# ---- control ----
INSTALLED_SIZE=$(du -sk "$PKG" --exclude=DEBIAN | cut -f1)
cat > "$PKG/DEBIAN/control" <<EOF
Package: aurora-music
Version: $VERSION
Section: sound
Priority: optional
Architecture: all
Installed-Size: $INSTALLED_SIZE
Depends: python3 (>= 3.9), python3-pyside6.qtwidgets, python3-pyside6.qtgui, python3-pyside6.qtcore, python3-pyside6.qtmultimedia, python3-pyside6.qtsvg
Recommends: python3-mutagen, python3-pip, ffmpeg, yt-dlp
Suggests:
Maintainer: Aurora Project <aurora@localhost>
Homepage: https://github.com/devrath/Material-3-Design-Kit
Description: Lightweight Material 3 music player
 Aurora Music is a fast, native Qt music player with a full
 Material Design 3 dark theme. Runs smoothly on low-spec
 hardware (4 GB RAM / Intel Celeron). Features: library scan,
 full playlist management, queue editing, live hue-slider
 theming, animated beat-graph visualizer, search, MPRIS media
 keys, system tray, agent-friendly CLI (queue/playlist/theme),
 playback via QtMultimedia. v17.5 adds Browse: online iTunes
 search with infinite scroll, auto-suggestions, FULL-TRACK downloads
 (yt-dlp + ffmpeg), and multi-strategy YouTube bot-protection bypass
 (cookies-from-browser, cookies.txt, client-rotation, Invidious,
 SAPISIDHASH Innertube, plain yt-dlp) to ~/Downloads/.
EOF

# ---- postinst: optional MPRIS support via pip (never fatal) ----
cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
# Optional: MPRIS media-key support (package not in Debian repos)
if command -v pip3 >/dev/null 2>&1; then
  pip3 install --quiet --break-system-packages mpris_server >/dev/null 2>&1 || \
    echo "aurora-music: MPRIS support skipped (pip install mpris_server failed — app still works)"
fi
# v17.5: yt-dlp is REQUIRED for Browse full-track downloads (ffmpeg is a
# hard Recommends in the control file). Install yt-dlp via pip if not present.
# v17.5 adds multi-strategy bot-bypass (cookies-from-browser, cookies.txt,
# client-rotation, Invidious, SAPISIDHASH Innertube, plain yt-dlp).
if ! command -v yt-dlp >/dev/null 2>&1; then
  if command -v pip3 >/dev/null 2>&1; then
    pip3 install --quiet --break-system-packages yt-dlp >/dev/null 2>&1 || \
      echo "aurora-music: yt-dlp install skipped — Browse downloads will not work until you run: pip3 install --break-system-packages yt-dlp"
  fi
fi
# refresh icon/desktop caches if tools exist
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q /usr/share/icons/hicolor || true
exit 0
EOF
chmod 755 "$PKG/DEBIAN/postinst"

# ---- build ----
mkdir -p "$OUT"
dpkg-deb --build --root-owner-group "$PKG" "$OUT/aurora-music_${VERSION}_all.deb"
echo "[build_deb] DONE -> $OUT/aurora-music_${VERSION}_all.deb"
dpkg-deb -I "$OUT/aurora-music_${VERSION}_all.deb"

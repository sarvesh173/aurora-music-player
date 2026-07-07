#!/usr/bin/env bash
# Aurora Music — AppImage builder
# Prerequisites: pip install pyinstaller, wget
# Usage: bash linux-packages/build-appimage.sh
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
SRC="$ROOT/aurora-player"
BUILD="/tmp/aurora-appimage-build"
rm -rf "$BUILD"; mkdir -p "$BUILD"
# 1. Build PyInstaller spec
cat > "$BUILD/aurora.spec" << SPECEOF
# -*- mode: python ; coding: utf-8 -*-
a = Analysis(['$SRC/aurora_player.py'],
    pathex=[],
    binaries=[],
    datas=[('$SRC/icon-256.png', '.'), ('$SRC/icon-512.png', '.')],
    hiddenimports=['PySide6.QtMultimedia', 'PySide6.QtSvg', 'PySide6.QtNetwork'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='aurora-music',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, icon='$SRC/icon-512.png')
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='aurora-music')
SPECEOF
# 2. Run PyInstaller
cd "$BUILD"
pyinstaller aurora.spec --noconfirm
# 3. Download appimagetool
wget -q -O appimagetool "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
chmod +x appimagetool
# 4. Create AppDir
mkdir -p AppDir/usr/bin AppDir/usr/share/applications AppDir/usr/share/icons/hicolor/512x512/apps
cp -r dist/aurora-music/* AppDir/usr/bin/
cp "$SRC/icon-512.png" AppDir/usr/share/icons/hicolor/512x512/apps/aurora-music.png
cat > AppDir/aurora-music.desktop << DESKTOPEOF
[Desktop Entry]
Type=Application
Name=Aurora Music
GenericName=Music Player
Exec=aurora-music
Icon=aurora-music
Terminal=false
Categories=AudioVideo;Audio;Player;
DESKTOPEOF
cat > AppDir/AppRun << 'RUNEOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/aurora-music" "$@"
RUNEOF
chmod +x AppDir/AppRun
# 5. Build AppImage
ARCH=$(uname -m)
./appimagetool AppDir "aurora-music-${ARCH}.AppImage"
echo "AppImage built: aurora-music-${ARCH}.AppImage"

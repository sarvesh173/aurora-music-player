#!/usr/bin/env bash
# v12.1: removed 'set -e' so pip warnings don't abort the whole install.
# The pip install has its own error handling below.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INST="$HOME/.local/share/aurora-player"
WRAP="$HOME/.local/bin/aurora-player"
DESK="$HOME/.local/share/applications/aurora-player.desktop"

# v17.5 version (kept in sync with APP_VERSION in aurora_player.py)
AURORA_VERSION="17.5.0"

echo "[Aurora] Installing v${AURORA_VERSION}..."

# v12.1 FIX: use 'python3 -m pip' which is more reliable than bare 'pip' on
# systems where pip is reserved for system Python or where pip3 isn't on PATH.
# --break-system-packages allows installing into the system Python on PEP 668
# systems (Debian 12+, Ubuntu 23.04+, Kali 2024+).
python3 -m pip install -r "$DIR/requirements.txt" --break-system-packages 2>&1 | tail -5 || {
  echo "[Aurora] WARN: pip install reported failures. Continuing anyway —"
  echo "[Aurora]       if PySide6/mpris_server are missing, install manually:"
  echo "[Aurora]       python3 -m pip install --break-system-packages PySide6 mpris_server mutagen"
}
mkdir -p "$INST" "$(dirname "$WRAP")" "$(dirname "$DESK")"
cp "$DIR/aurora_player.py" "$INST/"; chmod +x "$INST/aurora_player.py"
cat > "$WRAP" <<EOF
#!/usr/bin/env bash
exec python3 "$INST/aurora_player.py" "\$@"
EOF
chmod +x "$WRAP"
cat > "$DESK" <<EOF
[Desktop Entry]
Name=Aurora Music Player
Comment=Lightweight AI-agent-friendly music player v${AURORA_VERSION}
Exec=$WRAP
Icon=audio-x-generic
Terminal=false
Type=Application
Categories=Audio;Music;Player;AudioVideo;
EOF
mkdir -p "$HOME/Downloads"
echo "[Aurora] Done. Run: aurora-player --version"
echo "[Aurora] If 'command not found', run: export PATH=\"$HOME/.local/bin:$PATH\""
# Patch mpris_server metadata unpacking bug
cat << 'PYEOF' > /tmp/patch_mpris.py
import os, sys
def patch():
    try:
        import mpris_server.mpris.metadata as m
        file_path = m.__file__
    except ImportError:
        return
    with open(file_path, 'r') as f:
        content = f.read()
    old_line = "  album, art_url, artists, disc_number, length, name, track_id, track_number, _, uri = track\n"
    new_line = "  album, art_url, artists, comments, disc_number, length, name, track_id, track_number, type_, uri = track\n"
    if old_line in content:
        content = content.replace(old_line, new_line)
        with open(file_path, 'w') as f:
            f.write(content)
if __name__ == "__main__":
    patch()
PYEOF
python3 /tmp/patch_mpris.py
rm /tmp/patch_mpris.py

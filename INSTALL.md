# Aurora Music Player v17.5 — Install Guide

## ⚡ Easiest: install the .deb (Kali / Debian / Ubuntu)

A ready-built package ships in the `packages/` folder:

```bash
sudo apt install ./packages/aurora-music_17.5.0_all.deb
aurora-music        # or find "Aurora Music" in your app menu
```

apt automatically pulls the Qt dependencies. To remove:
`sudo apt remove aurora-music`

Want an AppImage or to rebuild the .deb? See `skill/PACKAGING_AGENT_PROMPT.md`
and `packaging/build_deb.sh`.

---

Material 3 edition. Works on Debian 12+, Ubuntu 23.04+, Kali 2024+, Fedora,
Arch — any Linux with Python 3.9+ and a desktop session.

## 1. Quick install (recommended)

```bash
unzip aurora-music-v17.5-complete.zip -d ~/aurora-music
cd ~/aurora-music/aurora-player
bash install.sh
```

What it does:
- installs Python deps (`PySide6`, `mpris_server`, `mutagen`)
- copies the player to `~/.local/share/aurora-player/`
- creates the `aurora-player` command in `~/.local/bin/`
- adds a desktop launcher (app menu entry)

Verify:

```bash
aurora-player --version     # → 17.5.0
aurora-player               # launches the Material 3 UI
```

If `command not found`:

```bash
export PATH="$HOME/.local/bin:$PATH"     # add to ~/.bashrc or ~/.zshrc
```

## 2. Manual install

```bash
python3 -m pip install --break-system-packages PySide6 mpris_server mutagen
python3 aurora-player/aurora_player.py
```

`--break-system-packages` is needed on PEP 668 systems (Debian 12+/Ubuntu
23.04+). Alternatively use a venv:

```bash
python3 -m venv ~/.aurora-venv
~/.aurora-venv/bin/pip install PySide6 mpris_server mutagen
~/.aurora-venv/bin/python aurora-player/aurora_player.py
```

## 3. System packages (only if Qt fails to start)

```bash
# Debian/Ubuntu/Kali
sudo apt install libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1
# Agent control (optional but recommended)
sudo apt install playerctl
```

## 4. First run

- Music library: drop audio files in `~/Downloads/` (auto-scan every 30s).
  Supported: mp3, m4a, flac, ogg, wav, opus, aac, wma.
- Settings live in `~/.aurora-player/`.

## 5. Agent / CLI control

```bash
aurora-player --status          # JSON playback status
aurora-player --toggle          # play/pause
aurora-player --play | --pause | --stop | --next | --prev
playerctl --player=aurora play  # MPRIS (needs playerctl)
```

## 6. Upgrading from v12.2

Just re-run `bash install.sh` — it overwrites the installed player.
Settings and playlists in `~/.aurora-player/` are preserved. v17.5 is a
pure UI upgrade (Material 3); no behavior or IPC changes.

## 7. Uninstall

```bash
rm -rf ~/.local/share/aurora-player ~/.local/bin/aurora-player \
       ~/.local/share/applications/aurora-player.desktop ~/.aurora-player
```

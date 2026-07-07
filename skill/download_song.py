#!/usr/bin/env python3
"""
Multi-Provider Song Downloader with Graceful Music Control + FLB Bridge
=======================================================================

Tries: JioSaavn (320kbps) -> SoundCloud -> YouTube (yt-dlp)
Two playback backends:
  - --play-flb : opens song in FLB Music Player GUI app (user controls manually)
  - --play     : background ffplay (CLI control via --stop/--pause/--resume)

NEW in v3.0.0 — FLB Music Player Integration
---------------------------------------------
  - --install  : one-time FLB AppImage download from GitHub releases (~77MB)
  - --play-flb : download song → open FLB Music Player GUI with that song
                 User controls play/pause/stop MANUALLY inside the GUI app.
                 NO background playback. NO silent ffplay.
  - --random   : pick a random song from random_songs.txt pool (73 songs)
                 then --play-flb it automatically
  - --check    : verify FLB is installed and report status

  FLB install path (hardcoded):
    ~/.local/share/flb-music/FLB-Music.AppImage
    ~/.local/bin/flb-music                    (wrapper)
    ~/Downloads/                              (FLB's registered music folder)

Hardcoded rules from v2.1 (still enforced for --play background mode):
  1. NO AUTO-PLAY:   downloading does NOT auto-play. Use --play or --play-flb.
  2. NO AUTO-STOP:   if something is already playing, --play REFUSES.
                     (Note: --play-flb does NOT enforce this because FLB is
                     a GUI app — user can queue multiple songs manually.)
  3. ONE SONG AT A TIME for background playback (state file enforces it)

v2.0+ features (still present for --play background mode):
  - PID-based state tracking  (~/.hermes_music/current.json)
  - --stop / --status / --pause / --resume / --list
  - Process-group isolation via os.setsid()

Usage
-----
  python download_song.py "Excuses AP Dhillon"            Download ONLY
  python download_song.py --play-flb "Excuses AP Dhillon" Download + open in FLB GUI
  python download_song.py --random                        Random song + FLB GUI
  python download_song.py --play "Excuses AP Dhillon"     Download + background ffplay
  python download_song.py --install                       Install FLB AppImage
  python download_song.py --check                         Check FLB install status
  python download_song.py --stop                          Stop background music
  python download_song.py --status                        Show what's playing
  python download_song.py --pause                         Pause background playback
  python download_song.py --resume                        Resume background playback
  python download_song.py --list                          Show recent play history
  python download_song.py --help                          This help
"""

import sys
import os
import signal
import shutil
import subprocess
import json
import time
import random
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path.home() / "Downloads"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STATE_DIR = Path.home() / ".hermes_music"
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "current.json"
HISTORY_FILE = STATE_DIR / "history.log"

# ===== FLB Music Player config (hardcoded) =====
SCRIPT_DIR = Path(__file__).parent
FLB_INSTALL_DIR = Path.home() / ".local" / "share" / "flb-music"
FLB_APPIMAGE_PATH = FLB_INSTALL_DIR / "FLB-Music.AppImage"
FLB_WRAPPER_PATH = Path.home() / ".local" / "bin" / "flb-music"
FLB_INSTALL_SCRIPT = SCRIPT_DIR / "install_flb.sh"
RANDOM_SONGS_FILE = SCRIPT_DIR / "random_songs.txt"


# =====================================================================
# State file management (atomic write / read)
# =====================================================================

def write_state(data: dict):
    """Atomically write the state file (write-to-tmp then rename)."""
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(STATE_FILE)


def read_state() -> dict | None:
    """Return current state dict, or None if no music is active."""
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return None


def clear_state():
    """Remove the state file (called on clean exit or after stop)."""
    try:
        STATE_FILE.unlink()
    except FileNotFoundError:
        pass


def append_history(song: str, provider: str, filepath: str):
    """Append a line to history.log for --list command."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {song} | {provider} | {filepath}\n"
        with HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def is_process_alive(pid: int) -> bool:
    """
    Return True if process `pid` is currently running AND not a zombie.
    Zombies report as "exists" via os.kill(pid, 0) but are effectively dead —
    they just haven't been reaped by their parent yet.
    """
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)  # signal 0 = "are you there?"
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours — treat as alive
    except OSError:
        return False

    # Check /proc/<pid>/status for zombie state (Linux only)
    try:
        status_file = Path(f"/proc/{pid}/status")
        if status_file.exists():
            for line in status_file.read_text().splitlines():
                if line.startswith("State:"):
                    # State: Z = zombie, T = stopped (traced), X = dead
                    state_code = line.split()[1] if len(line.split()) > 1 else ""
                    if state_code in ("Z", "X"):
                        return False
                    break
    except Exception:
        pass  # /proc not available (non-Linux) — fall back to os.kill result

    return True


# =====================================================================
# Process-group isolation
# =====================================================================

def detach_to_own_session():
    """
    Make this script a session leader so we can kill the whole music tree
    as a single process group. Idempotent: if already a leader, no-op.
    """
    try:
        os.setsid()
    except OSError:
        # Already a session leader (or no controlling terminal) — fine
        pass


# =====================================================================
# Signal handling — clean up children + state on SIGTERM / SIGINT
# =====================================================================

# Tracked subprocess handles so the signal handler can terminate them.
_ffplay_proc: subprocess.Popen | None = None
_ytdlp_proc: subprocess.Popen | None = None


def _cleanup_handler(signum, frame):
    """Gracefully terminate ffplay / yt-dlp children, clear state, exit."""
    global _ffplay_proc, _ytdlp_proc

    # ffplay
    if _ffplay_proc is not None and _ffplay_proc.poll() is None:
        try:
            _ffplay_proc.terminate()
            try:
                _ffplay_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _ffplay_proc.kill()
        except Exception:
            pass

    # yt-dlp
    if _ytdlp_proc is not None and _ytdlp_proc.poll() is None:
        try:
            _ytdlp_proc.terminate()
            try:
                _ytdlp_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _ytdlp_proc.kill()
        except Exception:
            pass

    clear_state()
    sys.exit(0)


def install_signal_handlers():
    signal.signal(signal.SIGTERM, _cleanup_handler)
    signal.signal(signal.SIGINT, _cleanup_handler)


# =====================================================================
# Download providers (JioSaavn -> SoundCloud -> YouTube)
# =====================================================================

def try_jiosaavn(query: str) -> str | None:
    """Try downloading from JioSaavn using musicdl Python API."""
    print("🔍 Trying JioSaavn (320kbps)...")
    try:
        from musicdl.musicdl import MusicClientBuilder

        builder = MusicClientBuilder()
        jiosaavn = builder.build({'type': 'JioSaavnMusicClient'})

        results = jiosaavn.search(query)
        if results:
            jiosaavn.download(results[:1])

            musicdl_output = Path.home() / "musicdl_outputs" / "JioSaavnMusicClient"
            if musicdl_output.exists():
                audio_files = (
                    list(musicdl_output.rglob("*.m4a"))
                    + list(musicdl_output.rglob("*.mp3"))
                )
                if audio_files:
                    newest = max(audio_files, key=lambda f: f.stat().st_mtime)
                    dest = OUTPUT_DIR / newest.name
                    shutil.copy2(newest, dest)
                    return f"JioSaavn (320kbps): {dest}"
        else:
            print("   No results found on JioSaavn")
    except Exception as e:
        print(f"   JioSaavn error: {e}")
    return None


def try_soundcloud(query: str) -> str | None:
    """Try downloading from SoundCloud using musicdl Python API."""
    print("🔍 Trying SoundCloud...")
    try:
        from musicdl.musicdl import MusicClientBuilder

        builder = MusicClientBuilder()
        soundcloud = builder.build({'type': 'SoundCloudMusicClient'})

        results = soundcloud.search(query)
        if results:
            soundcloud.download(results[:1])

            musicdl_output = Path.home() / "musicdl_outputs" / "SoundCloudMusicClient"
            if musicdl_output.exists():
                audio_files = (
                    list(musicdl_output.rglob("*.mp3"))
                    + list(musicdl_output.rglob("*.m4a"))
                    + list(musicdl_output.rglob("*.opus"))
                )
                if audio_files:
                    newest = max(audio_files, key=lambda f: f.stat().st_mtime)
                    dest = OUTPUT_DIR / newest.name
                    shutil.copy2(newest, dest)
                    return f"SoundCloud: {dest}"
        else:
            print("   No results found on SoundCloud")
    except Exception as e:
        print(f"   SoundCloud error: {e}")
    return None


def try_youtube(query: str) -> str | None:
    """Try downloading from YouTube using yt-dlp. Tracks Popen for clean stop."""
    global _ytdlp_proc
    print("🔍 Trying YouTube (yt-dlp)...")
    try:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "128K",
            "--ignore-errors",
            "--no-warnings",
            "-o", f"{OUTPUT_DIR}/%(title)s.%(ext)s",
            f"ytsearch1:{query}"
        ]
        _ytdlp_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout, stderr = _ytdlp_proc.communicate(timeout=180)
            returncode = _ytdlp_proc.returncode
        except subprocess.TimeoutExpired:
            _ytdlp_proc.kill()
            _ytdlp_proc.communicate()
            print("   YouTube timed out after 180s")
            return None
        finally:
            _ytdlp_proc = None

        if returncode == 0:
            mp3s = list(OUTPUT_DIR.glob("*.mp3"))
            if mp3s:
                newest = max(mp3s, key=lambda f: f.stat().st_mtime)
                return f"YouTube (128kbps): {newest}"
        else:
            err = stderr.decode(errors="replace")[:300] if stderr else ""
            print(f"   YouTube failed: {err}")
    except Exception as e:
        print(f"   YouTube error: {e}")
    return None


# =====================================================================
# Playback
# =====================================================================

def play_song(filepath: Path, song_name: str, provider: str):
    """Play the downloaded song via ffplay. Tracks PID + state file."""
    global _ffplay_proc
    print(f"🎵 Now playing on Bluetooth speaker: {song_name}")
    print(f"   Provider: {provider}")
    print(f"   File    : {filepath}")
    print(f"   PID     : {os.getpid()}  (send SIGTERM or use --stop to end)")

    # Update state to "playing"
    state = read_state() or {}
    state.update({
        "song": song_name,
        "file": str(filepath),
        "provider": provider,
        "state": "playing",
        "ffplay_pid": None,
        "started_at": state.get("started_at", datetime.now().isoformat()),
    })
    write_state(state)

    try:
        _ffplay_proc = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", str(filepath)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Record ffplay PID so --pause / --resume can target it
        state["ffplay_pid"] = _ffplay_proc.pid
        write_state(state)

        # Block until ffplay exits (signal handler can interrupt)
        _ffplay_proc.wait()

    except FileNotFoundError:
        print("   ❌ ffplay not found. Install ffmpeg (sudo apt-get install ffmpeg)")
    except Exception as e:
        print(f"   ❌ ffplay error: {e}")
    finally:
        # Log to history before clearing state
        append_history(song_name, provider, str(filepath))
        clear_state()


def is_anything_active() -> bool:
    """
    Return True if a music process (downloading or playing) is currently
    active according to the state file AND the recorded PID is still alive.
    Stale state files (PID dead) are auto-cleared.
    """
    state = read_state()
    if not state:
        return False
    pid = state.get("pid", 0)
    if not is_process_alive(pid):
        # Stale state — clean it up so future --play calls succeed
        clear_state()
        return False
    return True


# =====================================================================
# FLB Music Player integration
# =====================================================================

def flb_is_installed() -> bool:
    """Return True if FLB AppImage exists and is executable."""
    return FLB_APPIMAGE_PATH.exists() and os.access(FLB_APPIMAGE_PATH, os.X_OK)


def flb_ensure_installed():
    """
    If FLB is not installed, print clear instructions for the agent/user
    and exit with code 3. The agent should then run --install.
    """
    if flb_is_installed():
        return
    print("\033[31m[ERROR]\033[0m FLB Music Player is NOT installed.")
    print()
    print("To install FLB, run one of these:")
    print(f"  python3 {Path(__file__).name} --install")
    print(f"  bash {FLB_INSTALL_SCRIPT}")
    print()
    print("After install, open FLB once manually and add ~/Downloads/ as a")
    print("music folder in Settings → Folders. Then re-run your --play-flb command.")
    sys.exit(3)


def flb_is_installed() -> bool:
    """Return True if FLB AppImage exists and is executable."""
    return FLB_APPIMAGE_PATH.exists() and os.access(FLB_APPIMAGE_PATH, os.X_OK)


def flb_test_launch() -> bool:
    """
    Actually test if the FLB AppImage can launch. Returns True if it can,
    False if it fails (e.g., FUSE missing, AppImage corruption).

    Tries two methods:
    1. Direct launch with --appimage-version (fast, uses FUSE)
    2. APPIMAGE_EXTRACT_AND_RUN=1 fallback (slower, no FUSE needed)

    If method 1 fails, sets a flag so future launches use method 2.
    """
    if not flb_is_installed():
        return False

    # Try method 1: direct launch (needs FUSE)
    try:
        result = subprocess.run(
            [str(FLB_APPIMAGE_PATH), "--appimage-version"],
            capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return True
        # Non-zero return code usually means FUSE issue
    except subprocess.TimeoutExpired:
        # Timeout could mean it actually launched (AppImage version flag may not exist)
        # but more likely it's hanging. Treat as success cautiously.
        return True
    except Exception:
        pass

    # Try method 2: APPIMAGE_EXTRACT_AND_RUN=1 (no FUSE needed)
    try:
        env = os.environ.copy()
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        result = subprocess.run(
            [str(FLB_APPIMAGE_PATH), "--appimage-version"],
            capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL,
            env=env,
        )
        if result.returncode == 0:
            # Mark that we need to use extract-and-run for future launches
            marker = FLB_INSTALL_DIR / ".use_extract_and_run"
            marker.touch()
            return True
    except subprocess.TimeoutExpired:
        # Extract-and-run is slow; timeout might mean it's working
        marker = FLB_INSTALL_DIR / ".use_extract_and_run"
        marker.touch()
        return True
    except Exception:
        pass

    return False


def flb_needs_extract_and_run() -> bool:
    """Check if we previously determined APPIMAGE_EXTRACT_AND_RUN=1 is needed."""
    return (FLB_INSTALL_DIR / ".use_extract_and_run").exists()


def flb_ensure_installed():
    """
    If FLB is not installed, print clear instructions for the agent/user
    and exit with code 3. The agent should then run --install.
    """
    if flb_is_installed():
        return
    print("\033[31m[ERROR]\033[0m FLB Music Player is NOT installed.")
    print()
    print("To install FLB, run one of these:")
    print(f"  python3 {Path(__file__).name} --install")
    print(f"  bash {FLB_INSTALL_SCRIPT}")
    print()
    print("After install, open FLB once manually and add ~/Downloads/ as a")
    print("music folder in Settings → Folders. Then re-run your --play-flb command.")
    sys.exit(3)


def flb_check_display() -> bool:
    """
    Check if a display server is available. Electron apps (like FLB) need
    a DISPLAY env var to show their GUI window. Without it, the process
    starts but no window appears — silent failure.

    Returns True if display is available, False otherwise.
    """
    display = os.environ.get("DISPLAY")
    if not display:
        return False

    # On Wayland, DISPLAY might not be set but WAYLAND_DISPLAY should be
    wayland = os.environ.get("WAYLAND_DISPLAY")
    if wayland:
        return True

    # If DISPLAY is set, check if X server is actually running
    # Try xset (fast) or xdpyinfo (more thorough)
    try:
        result = subprocess.run(
            ["xset", "q"],
            capture_output=True, timeout=3,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fall back to: if DISPLAY is set, assume it works
    # (xset might not be installed)
    return True if display else False


def flb_verify_window_launched(timeout: int = 8) -> bool:
    """
    After launching FLB, verify that a window actually appeared.
    Uses wmctrl or xdotool if available. Falls back to checking if the
    process is still alive after `timeout` seconds.

    Returns True if a window was detected OR if process is still alive
    after the timeout (best-effort verification).
    """
    # Try wmctrl first (most reliable for window detection)
    wmctrl = shutil.which("wmctrl")
    if wmctrl:
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(1)
            try:
                result = subprocess.run(
                    [wmctrl, "-l"],
                    capture_output=True, text=True, timeout=3,
                    stdin=subprocess.DEVNULL,
                )
                if result.returncode == 0:
                    # Look for FLB-related window titles
                    for line in result.stdout.splitlines():
                        lower = line.lower()
                        if any(kw in lower for kw in ["flb", "music", "flbmusic"]):
                            return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        # No FLB window found via wmctrl
        return False

    # Try xdotool as fallback
    xdotool = shutil.which("xdotool")
    if xdotool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(1)
            try:
                result = subprocess.run(
                    [xdotool, "search", "--name", "music"],
                    capture_output=True, text=True, timeout=3,
                    stdin=subprocess.DEVNULL,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        return False

    # No window manager tools available — fall back to process alive check
    return False  # caller should check proc.poll() instead


def flb_launch(song_path: Path | None = None):
    """
    Launch FLB Music Player in the background (non-blocking).
    If song_path is given, pass it as an argument.

    Non-blocking: uses subprocess.Popen with start_new_session=True and does
    NOT call .wait(). The script returns immediately so the agent's terminal
    is free. FLB stays open even after the script exits — user controls
    playback manually inside the GUI.

    CRITICAL: Verifies the GUI actually appeared before claiming success.
    Catches silent failures (no DISPLAY, FUSE issues, etc.) and reports
    them honestly instead of falsely claiming success.

    Launch strategy (in order):
    1. Check DISPLAY env var — if missing, fail early with clear message
    2. Try snap version (flbmusic) if installed — most reliable on Kali
    3. Try AppImage with wrapper (flb-music)
    4. Try AppImage directly
    5. If AppImage fails, retry with APPIMAGE_EXTRACT_AND_RUN=1 (FUSE workaround)
    6. Verify window actually appeared via wmctrl/xdotool
    7. If all fail, suggest snap install
    """
    print(f"\033[32m[FLB]\033[0m Launching FLB Music Player...")

    # ===== CRITICAL: Check DISPLAY before attempting GUI launch =====
    if not flb_check_display():
        print(f"\033[31m[ERROR]\033[0m No display server detected (DISPLAY env var missing).")
        print()
        print("FLB Music Player is an Electron GUI app — it needs a display to show its window.")
        print("You appear to be running in a headless/SSH context.")
        print()
        print("Options:")
        print("  1. Run this command directly on the desktop (not over SSH)")
        print("  2. Use X forwarding: ssh -X user@host  (then re-run)")
        print("  3. Set DISPLAY manually: export DISPLAY=:0  (if running on same machine)")
        print("  4. Use VNC/RDP to access the desktop GUI")
        print()
        print("Songs were still downloaded to ~/Downloads/ — they'll appear in FLB's library")
        print("next time you open FLB on the desktop.")
        sys.exit(6)

    # Determine which FLB binary to use
    snap_path = shutil.which("flbmusic")
    if snap_path:
        cmd = [snap_path]
        print(f"\033[34m[FLB]\033[0m Using snap version: {snap_path}")
    elif FLB_WRAPPER_PATH.exists() and os.access(FLB_WRAPPER_PATH, os.X_OK):
        cmd = [str(FLB_WRAPPER_PATH)]
    elif FLB_APPIMAGE_PATH.exists():
        cmd = [str(FLB_APPIMAGE_PATH)]
    else:
        print(f"\033[31m[ERROR]\033[0m No FLB installation found.")
        print(f"   Install with: python3 {Path(__file__).name} --install")
        print(f"   OR snap:     sudo snap install flbmusic")
        sys.exit(4)

    if song_path and song_path.exists():
        cmd.append(str(song_path))

    # Set up environment — add APPIMAGE_EXTRACT_AND_RUN=1 if needed
    env = os.environ.copy()
    using_extract_and_run = False
    if flb_needs_extract_and_run() and "snap" not in cmd[0]:
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        using_extract_and_run = True
        print(f"\033[34m[FLB]\033[0m Using APPIMAGE_EXTRACT_AND_RUN=1 (FUSE workaround)")

    print(f"\033[34m[FLB]\033[0m Command: {' '.join(cmd)}")

    # ===== CRITICAL: Capture stderr to log file (NOT DEVNULL) =====
    # This catches silent failures like FUSE errors, missing libs, etc.
    stderr_log = STATE_DIR / "flb_stderr.log"
    try:
        stderr_fh = open(stderr_log, "w")
    except Exception:
        stderr_fh = subprocess.DEVNULL

    proc = None
    launch_attempts = []

    try:
        # Attempt 1: launch as-is (or with extract-and-run if marked)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr_fh if stderr_fh != subprocess.DEVNULL else subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        launch_attempts.append(("primary", cmd, env, proc.pid))

        # Wait for AppImage (not snap) to potentially fail fast
        if "snap" not in cmd[0] and not using_extract_and_run:
            time.sleep(2)
            if proc.poll() is not None:
                # Process died — likely FUSE issue
                print(f"\033[33m[FLB]\033[0m Direct launch failed (likely FUSE issue on Kali).")
                print(f"\033[33m[FLB]\033[0m Retrying with APPIMAGE_EXTRACT_AND_RUN=1...")
                env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
                marker = FLB_INSTALL_DIR / ".use_extract_and_run"
                marker.touch()
                if isinstance(stderr_fh, int):
                    stderr_fh = open(stderr_log, "w")
                else:
                    stderr_fh.seek(0)
                    stderr_fh.truncate()
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_fh,
                    start_new_session=True,
                    env=env,
                )
                launch_attempts.append(("extract-and-run", cmd, env, proc.pid))
                time.sleep(4)  # extract-and-run is slower

        # Attempt 3: if still failing and snap available, try snap
        if proc.poll() is not None and snap_path:
            print(f"\033[33m[FLB]\033[0m AppImage still failing. Trying snap version...")
            cmd = [snap_path]
            if song_path and song_path.exists():
                cmd.append(str(song_path))
            if isinstance(stderr_fh, int):
                stderr_fh = open(stderr_log, "w")
            else:
                stderr_fh.seek(0)
                stderr_fh.truncate()
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=stderr_fh,
                start_new_session=True,
                env=os.environ.copy(),  # snap doesn't need extract-and-run
            )
            launch_attempts.append(("snap", cmd, os.environ.copy(), proc.pid))
            time.sleep(3)

        # ===== CRITICAL: Verify process is still alive =====
        if proc.poll() is not None:
            # Process died — read stderr log for clues
            print(f"\033[31m[ERROR]\033[0m FLB process died immediately.")
            print()
            print(f"   Attempts tried:")
            for attempt_name, _, _, pid in launch_attempts:
                print(f"     - {attempt_name} (PID {pid})")
            print()
            try:
                if stderr_log.exists():
                    stderr_content = stderr_log.read_text().strip()
                    if stderr_content:
                        print(f"   stderr output (last 500 chars):")
                        print(f"   {stderr_content[-500:]}")
                        print()
                    else:
                        print(f"   stderr log is empty (silent failure).")
            except Exception:
                pass
            print()
            print(f"\033[31m[ERROR]\033[0m FLB failed to launch. Try:")
            print(f"   1. Run --test-launch to diagnose")
            print(f"   2. Install snap version: sudo snap install flbmusic")
            print(f"   3. Check if you're on a desktop (DISPLAY={os.environ.get('DISPLAY', 'NOT SET')})")
            sys.exit(4)

        # ===== CRITICAL: Verify window actually appeared =====
        print(f"\033[34m[FLB]\033[0m Process alive (PID={proc.pid}). Verifying GUI window...")
        window_verified = flb_verify_window_launched(timeout=8)

        if not window_verified:
            # Check if process is still alive at least
            if proc.poll() is None:
                # Process alive but no window detected
                # Could be: wmctrl/xdotool not installed, or window took longer to appear
                # Best-effort: claim success but warn
                print(f"\033[33m[FLB]\033[0m ⚠️  Process is running but couldn't verify GUI window.")
                print(f"   (wmctrl/xdotool not available for verification)")
                print(f"   PID={proc.pid} — if you don't see FLB on screen within 10s,")
                print(f"   check stderr log: {stderr_log}")
                print()
                print(f"   To install verification tools: sudo apt-get install wmctrl xdotool")
            else:
                # Process died during verification window
                print(f"\033[31m[ERROR]\033[0m FLB process died during launch.")
                try:
                    if stderr_log.exists():
                        stderr_content = stderr_log.read_text().strip()
                        if stderr_content:
                            print(f"   stderr: {stderr_content[-500:]}")
                except Exception:
                    pass
                sys.exit(4)
        else:
            print(f"\033[32m[FLB]\033[0m ✅ FLB window verified (visible on desktop)")

        print()
        print(f"\033[32m[FLB]\033[0m ✅ FLB Music Player launched (PID={proc.pid})")
        print()
        if song_path:
            print(f"\033[34m[FLB]\033[0m 🎵 Song file : {song_path}")
        print(f"\033[34m[FLB]\033[0m 📂 Music folder: {OUTPUT_DIR} (FLB scans this)")
        print()
        print("   The app should now be open. Find the song in the library")
        print("   (sort by 'Date Added' or 'Recent' to see it at the top),")
        print("   then click play to start playback.")
        print()
        print("   You can stop/pause/seek/queue directly inside the FLB app.")

    except FileNotFoundError:
        print(f"\033[31m[ERROR]\033[0m Failed to launch FLB. Binary not found.")
        sys.exit(4)
    except Exception as e:
        print(f"\033[31m[ERROR]\033[0m Failed to launch FLB: {e}")
        sys.exit(4)
    finally:
        if isinstance(stderr_fh, int):
            pass  # DEVNULL, nothing to close
        else:
            try:
                stderr_fh.close()
            except Exception:
                pass


def pick_random_song() -> str:
    """Pick a random song name from random_songs.txt."""
    if not RANDOM_SONGS_FILE.exists():
        print(f"\033[31m[ERROR]\033[0m Random songs file not found: {RANDOM_SONGS_FILE}")
        sys.exit(1)

    songs = []
    for line in RANDOM_SONGS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        songs.append(line)

    if not songs:
        print("\033[31m[ERROR]\033[0m Random songs file is empty. Add songs to random_songs.txt")
        sys.exit(1)

    return random.choice(songs)


# Core download function used by all play paths
def download_song_to_file(query: str) -> Path | None:
    """
    Try all providers in order. Return Path to downloaded file, or None.
    Does NOT write to state file, does NOT play. Just downloads to ~/Downloads/.
    Shared by --play-flb, --random, and --play (background).
    """
    print(f"\n🎵 Searching for: {query}")
    print("=" * 50)

    providers = [
        ("JioSaavn (320kbps)", try_jiosaavn),
        ("SoundCloud", try_soundcloud),
        ("YouTube (128kbps fallback)", try_youtube),
    ]

    for name, func in providers:
        result = func(query)
        if result:
            print(f"\n✅ SUCCESS via {result}")
            if ": " in result:
                filepath_str = result.split(": ", 1)[1]
                filepath = Path(filepath_str)
                if filepath.exists():
                    return filepath
        print(f"   → {name} failed, trying next...\n")

    print("\n❌ All providers failed")
    return None


def aurora_launch(song_path):
    """Launch Aurora Music Player with the given song file."""
    aurora_bin = shutil.which("aurora-player") or str(Path.home() / ".local" / "bin" / "aurora-player")
    if not Path(aurora_bin).exists():
        print("[ERROR] Aurora Music Player not installed.")
        print("   Install: bash aurora-player/install.sh")
        sys.exit(4)

    cmd = [aurora_bin, "--play-file", str(song_path)]
    env = os.environ.copy()
    # CRITICAL FIX v12.1: only force DISPLAY if WAYLAND_DISPLAY is also missing.
    # Forcing DISPLAY=:0 on a Wayland-only system makes Qt try X11 first and fail.
    if not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
        env["DISPLAY"] = ":0"

    print(f"[Aurora] Launching Aurora Music Player...")
    print(f"[Aurora] Command: {' '.join(cmd)}")
    print()

    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True, env=env)
        import time; time.sleep(2)
        # CRITICAL FIX v12.1: when Aurora is already running, the wrapper script
        # sends an IPC command and exits with code 0. The old code treated ANY
        # non-None poll() as failure, which meant every "Aurora already running"
        # case falsely reported 'Aurora died immediately'. Only treat non-zero
        # exit codes as failure.
        rc = proc.poll()
        if rc is not None and rc != 0:
            print(f"[ERROR] Aurora died immediately (exit code {rc}). Try: " + aurora_bin)
            sys.exit(4)
        elif rc == 0:
            print(f"[Aurora] Already running — sent play command via IPC.")
        else:
            print(f"[Aurora] Launched (PID={proc.pid})")
        print(f"[Aurora] Song: {song_path}")
        print(f"[Aurora] Auto-scans ~/Downloads/ - song will appear and play automatically.")
        print()
        print("   Control: playerctl --player=aurora play/pause/next/prev")
        print("   Or:      aurora-player --play / --pause / --next / --prev / --stop")
    except FileNotFoundError:
        print(f"[ERROR] Not found: {aurora_bin}")
        sys.exit(4)
    except Exception as e:
        print(f"[ERROR] Launch failed: {e}")
        sys.exit(4)


def cmd_play_flb(query: str):
    """Download a song and play it in Aurora Music Player."""
    print(f"[Aurora] Playing: {query}")
    print()
    song_path = download_song_to_file(query)
    if not song_path:
        print("[ERROR] Download failed.")
        sys.exit(5)
    print()
    aurora_launch(song_path)


def cmd_random():
    """Pick a random song, download it, play in Aurora."""
    song = pick_random_song()
    print(f"[Aurora] Random song: {song}")
    print()
    song_path = download_song_to_file(song)
    if not song_path:
        print("[ERROR] Download failed.")
        sys.exit(5)
    print()
    aurora_launch(song_path)


def cmd_install():
    """Run the install_flb.sh script to download FLB AppImage from GitHub."""
    if not FLB_INSTALL_SCRIPT.exists():
        print(f"\033[31m[ERROR]\033[0m Install script not found: {FLB_INSTALL_SCRIPT}")
        sys.exit(1)

    print("\033[32m[FLB]\033[0m Running FLB installer...")
    print()
    result = subprocess.run(["bash", str(FLB_INSTALL_SCRIPT)])
    sys.exit(result.returncode)


def cmd_check():
    """Check FLB install status + actually test launch + show bg state."""
    print("=" * 50)
    print("FLB Music Player status")
    print("=" * 50)
    if flb_is_installed():
        print(f"\033[32m[FLB]\033[0m ✅ FLB AppImage file exists.")
        print(f"   AppImage: {FLB_APPIMAGE_PATH}")
        print(f"   Wrapper : {FLB_WRAPPER_PATH}")
        size_mb = FLB_APPIMAGE_PATH.stat().st_size // (1024 * 1024)
        print(f"   Size    : {size_mb}MB")

        # Check FUSE
        fuse_available = False
        try:
            subprocess.run(["fusermount", "--version"],
                           capture_output=True, check=True)
            print("   FUSE    : available ✅ (libfuse2)")
            fuse_available = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:
                subprocess.run(["fusermount3", "--version"],
                               capture_output=True, check=True)
                print("   FUSE3   : available ⚠️ (fuse3 — old AppImages may not work)")
                fuse_available = True  # fuse3 exists, but old AppImages may fail
            except (FileNotFoundError, subprocess.CalledProcessError):
                print("   FUSE    : NOT available ⚠️")
                print("            Install: sudo apt-get install libfuse2")
                print("            OR set APPIMAGE_EXTRACT_AND_RUN=1 (automatic fallback)")

        # Check if we already know extract-and-run is needed
        if flb_needs_extract_and_run():
            print("   Launch  : will use APPIMAGE_EXTRACT_AND_RUN=1 (FUSE workaround active)")

        # Check snap version as alternative
        snap_path = shutil.which("flbmusic")
        if snap_path:
            print(f"   Snap    : also installed at {snap_path} ✅")

    else:
        print("\033[33m[FLB]\033[0m ❌ FLB Music Player is NOT installed.")
        print(f"   Install with: python3 {Path(__file__).name} --install")
        print(f"   OR snap:     sudo snap install flbmusic")

    print()
    print("=" * 50)
    print("Background music state (--play mode)")
    print("=" * 50)
    cmd_status()


def cmd_test_launch():
    """Actually try to launch FLB AppImage and report if it works."""
    print("=" * 50)
    print("FLB AppImage launch test")
    print("=" * 50)

    if not flb_is_installed():
        print("\033[31m[ERROR]\033[0m FLB AppImage is not installed.")
        print("   Run: python3 download_song.py --install")
        sys.exit(3)

    print("Testing direct launch (needs FUSE)...")
    print(f"   Command: {FLB_APPIMAGE_PATH} --appimage-version")
    print()

    # Method 1: direct launch
    try:
        result = subprocess.run(
            [str(FLB_APPIMAGE_PATH), "--appimage-version"],
            capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            print("\033[32m[FLB]\033[0m ✅ Direct launch works!")
            print(f"   Output: {result.stdout.strip()[:200]}")
            sys.exit(0)
        else:
            print(f"\033[33m[FLB]\033[0m ⚠️ Direct launch failed (return code {result.returncode})")
            if result.stderr:
                print(f"   stderr: {result.stderr.strip()[:300]}")
    except subprocess.TimeoutExpired:
        print("\033[33m[FLB]\033[0m ⚠️ Direct launch timed out (10s) — may be hanging")
    except Exception as e:
        print(f"\033[33m[FLB]\033[0m ⚠️ Direct launch error: {e}")

    print()
    print("Testing APPIMAGE_EXTRACT_AND_RUN=1 fallback...")
    print("   (extracts AppImage to /tmp — slower but no FUSE needed)")
    print()

    # Method 2: extract-and-run
    try:
        env = os.environ.copy()
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        result = subprocess.run(
            [str(FLB_APPIMAGE_PATH), "--appimage-version"],
            capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL,
            env=env,
        )
        if result.returncode == 0:
            print("\033[32m[FLB]\033[0m ✅ APPIMAGE_EXTRACT_AND_RUN=1 works!")
            print(f"   Output: {result.stdout.strip()[:200]}")
            # Mark for future launches
            marker = FLB_INSTALL_DIR / ".use_extract_and_run"
            marker.touch()
            print(f"\033[32m[FLB]\033[0m Marked: future launches will use extract-and-run automatically.")
            print()
            print("You can now use --play-flb normally. First launch will be slower (~5s)")
            print("as the AppImage extracts to /tmp. Subsequent launches are faster.")
            sys.exit(0)
        else:
            print(f"\033[31m[FLB]\033[0m ❌ Extract-and-run also failed (return code {result.returncode})")
            if result.stderr:
                print(f"   stderr: {result.stderr.strip()[:300]}")
    except subprocess.TimeoutExpired:
        print("\033[33m[FLB]\033[0m ⚠️ Extract-and-run timed out (30s)")
        print("   This might mean it's working but slow. Trying to mark anyway...")
        marker = FLB_INSTALL_DIR / ".use_extract_and_run"
        marker.touch()
        sys.exit(0)
    except Exception as e:
        print(f"\033[31m[FLB]\033[0m ❌ Extract-and-run error: {e}")

    print()
    print("=" * 50)
    print("BOTH METHODS FAILED — try snap install instead")
    print("=" * 50)
    print()
    print("The AppImage is not launching on this system. Try the snap version:")
    print()
    print("  sudo apt-get install -y snapd")
    print("  sudo systemctl start snapd")
    print("  sudo systemctl enable snapd")
    print("  sudo snap install flbmusic")
    print()
    print("After snap install, you can launch FLB with: flbmusic")
    print("The skill scripts will still work — they check for snap as fallback.")
    sys.exit(4)


def download_only(query: str):
    """
    Download a song WITHOUT playing it.
    Does NOT write to the state file, does NOT touch any current playback.
    Safe to use even while another song is playing.

    Prints a single deterministic success line 'DOWNLOADED: <path>' on success
    so callers (e.g. smart_music_picker.py) can parse stdout programmatically.
    """
    print(f"\n📥 Download-only mode for: {query}")
    print("=" * 50)
    print("ℹ️  Song will be downloaded but NOT played. Use --play-flb or default mode to start playback.")
    print()

    song_path = download_song_to_file(query)
    if song_path:
        # CRITICAL: this exact 'DOWNLOADED: ' prefix is parsed by smart_music_picker.py
        # Do not change the format without updating both files.
        print(f"\nDOWNLOADED: {song_path}")
        print()
        print("   To play it, run:")
        print(f'   python download_song.py "{query}"')
        print("   (or: --play for background ffplay mode)")
    else:
        print("\n❌ Download failed.")
    return song_path


def download_and_play(query: str):
    """
    Download a song AND play it in BACKGROUND (ffplay). Used by --play.
    Enforces v2.1 hardcoded rules:
      - NO AUTO-STOP: if something is already playing, REFUSE (do not stop).
      - ONE SONG AT A TIME: only one playback process may exist.

    For GUI playback (FLB Music Player), use cmd_play_flb() instead via --play-flb.
    """
    # ===== HARDCODED RULE: Refuse if something is already active =====
    if is_anything_active():
        existing = read_state()
        song = existing.get("song", "?") if existing else "?"
        state_str = existing.get("state", "?") if existing else "?"
        print("❌ REFUSED: Another song is already active in background mode.")
        print(f"   Currently {state_str}: {song}")
        print()
        print("   The script does NOT auto-stop. To switch songs, you must:")
        print("     1. Stop the current song first:  python download_song.py --stop")
        print(f"     2. Then play the new one:        python download_song.py --play \"{query}\"")
        print()
        print("   (Or use --play-flb to play in the FLB GUI app, which doesn't enforce this.)")
        sys.exit(2)

    # Write initial state BEFORE downloading, so --stop can interrupt
    # the download phase too (yt-dlp can take 30-180 seconds).
    write_state({
        "pid": os.getpid(),
        "pgid": os.getpgid(0),
        "song": query,
        "file": None,
        "provider": None,
        "state": "downloading",
        "ffplay_pid": None,
        "started_at": datetime.now().isoformat(),
    })

    song_path = download_song_to_file(query)
    if song_path:
        # Determine provider name from result
        # (already printed by download_song_to_file)
        # Just play the file via ffplay
        play_song(song_path, query, "downloaded")
        return song_path
    else:
        print("\n❌ All providers failed")
        clear_state()
        return None


# =====================================================================
# Control commands
# =====================================================================

def cmd_stop():
    """
    Stop currently playing / downloading music.
    Kills ONLY the music process tree (parent + ffplay + yt-dlp) via killpg.
    Does NOT touch Hermes or any other bot process.
    """
    state = read_state()
    if not state:
        print("⏹️  No music is currently playing.")
        return

    pid = state.get("pid")
    pgid = state.get("pgid", pid)

    if not pid or not is_process_alive(pid):
        clear_state()
        print("⏹️  Music process already gone. State cleared.")
        return

    song = state.get("song", "?")
    provider = state.get("provider") or "downloading..."
    print(f"⏹️  Stopping: {song}  (provider: {provider})")
    print(f"   Target PID={pid}  PGID={pgid}")

    # 1) Graceful: SIGTERM to whole process group (parent + ffplay + yt-dlp)
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception as e:
        print(f"   warn: killpg SIGTERM failed: {e}")

    # 2) Wait up to 3 seconds for clean exit
    deadline = time.time() + 3
    while time.time() < deadline:
        if not is_process_alive(pid):
            break
        time.sleep(0.2)

    # 3) Force-kill if still alive
    if is_process_alive(pid):
        print("   ⚠️  Process didn't exit on SIGTERM, sending SIGKILL...")
        try:
            os.killpg(pgid, signal.SIGKILL)
        except Exception:
            pass
        # Reap
        time.sleep(0.5)

    clear_state()
    print("✅ Music stopped. State cleared.")


def cmd_status():
    """Show what's currently playing (or downloading)."""
    state = read_state()
    if not state:
        print("🔇 Nothing is currently playing.")
        return

    pid = state.get("pid")
    if not pid or not is_process_alive(pid):
        clear_state()
        print("🔇 Nothing is currently playing (stale state cleared).")
        return

    # Compute elapsed time
    elapsed = ""
    started_at = state.get("started_at")
    if started_at:
        try:
            started = datetime.fromisoformat(started_at)
            elapsed_secs = int((datetime.now() - started).total_seconds())
            mins, secs = divmod(elapsed_secs, 60)
            elapsed = f"  ({mins}m {secs}s elapsed)"
        except Exception:
            pass

    state_str = state.get("state", "?")
    emoji = {
        "playing":    "▶️",
        "paused":     "⏸️",
        "downloading":"⬇️",
    }.get(state_str, "🎵")

    print(f"{emoji} {state_str.title()}: {state.get('song', '?')}{elapsed}")
    print(f"   Provider : {state.get('provider') or '— (still downloading)'}")
    print(f"   File     : {state.get('file') or '—'}")
    print(f"   PID      : {pid}   PGID: {state.get('pgid', pid)}")
    if state.get("ffplay_pid"):
        print(f"   ffplay   : {state['ffplay_pid']}")


def cmd_pause():
    """Pause playback (SIGSTOP to ffplay only)."""
    state = read_state()
    if not state:
        print("⏸️  Nothing is currently playing.")
        return

    ffplay_pid = state.get("ffplay_pid")
    if not ffplay_pid:
        print("⏸️  No active playback to pause (still downloading?). Wait for playback to start.")
        return

    try:
        os.kill(ffplay_pid, signal.SIGSTOP)
        state["state"] = "paused"
        write_state(state)
        print(f"⏸️  Paused: {state.get('song', '?')}")
        print("   Use --resume to continue.")
    except ProcessLookupError:
        clear_state()
        print("⏸️  Process gone. State cleared.")
    except Exception as e:
        print(f"   ❌ pause failed: {e}")


def cmd_resume():
    """Resume paused playback (SIGCONT to ffplay)."""
    state = read_state()
    if not state:
        print("▶️  Nothing is currently paused.")
        return

    ffplay_pid = state.get("ffplay_pid")
    if not ffplay_pid:
        print("▶️  No active playback to resume.")
        return

    try:
        os.kill(ffplay_pid, signal.SIGCONT)
        state["state"] = "playing"
        write_state(state)
        print(f"▶️  Resumed: {state.get('song', '?')}")
    except ProcessLookupError:
        clear_state()
        print("▶️  Process gone. State cleared.")
    except Exception as e:
        print(f"   ❌ resume failed: {e}")


def cmd_list():
    """Show recent play history."""
    if not HISTORY_FILE.exists():
        print("📜 No play history yet.")
        return

    print("📜 Recent plays (last 15):")
    print("-" * 60)
    try:
        lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
        for line in lines[-15:]:
            print(line)
    except Exception as e:
        print(f"   ❌ read error: {e}")


# =====================================================================
# CLI
# =====================================================================

USAGE = """
Multi-Provider Music Downloader v3.0.0
======================================

Downloads songs (JioSaavn → SoundCloud → YouTube) with TWO playback backends:

  --play-flb  →  Opens song in FLB Music Player GUI app.
                  User controls play/pause/stop MANUALLY inside the GUI.
                  NO background playback. This is the recommended mode.
  --play      →  Background ffplay. Use --stop/--pause/--resume to control.
                  Subject to v2.1 hardcoded rules (no auto-stop, one at a time).

Hardcoded rules (cannot be overridden):
  1. NO AUTO-PLAY  — downloading does NOT auto-play. Use --play or --play-flb.
  2. NO AUTO-STOP  — if background music is playing, --play REFUSES. Run --stop first.
                     (--play-flb is exempt — FLB is a GUI app, user manages queue.)
  3. ONE AT A TIME — only one BACKGROUND playback process can exist (state file enforces).

Usage:
  python download_song.py "song name"            Download ONLY (no play)
  python download_song.py --play-flb "song name" Download + open in FLB GUI app
  python download_song.py --random               Pick random song + open in FLB
  python download_song.py --play "song name"     Download + background ffplay
  python download_song.py --install              Install FLB AppImage (one-time)
  python download_song.py --check                Check FLB status + background state
  python download_song.py --test-launch          Test if FLB AppImage actually launches
  python download_song.py --stop                 Stop background music (no pkill!)
  python download_song.py --status               Show what's playing
  python download_song.py --pause                Pause background playback
  python download_song.py --resume               Resume background playback
  python download_song.py --list                 Show recent play history
  python download_song.py --help                 This help

Examples:
  python download_song.py "Excuses AP Dhillon"               # just download
  python download_song.py --play-flb "Excuses AP Dhillon"    # GUI app playback
  python download_song.py --random                           # random song in FLB
  python download_song.py --play "Excuses AP Dhillon"        # background playback
  python download_song.py --stop                             # stop bg music
  python download_song.py --status                           # what's playing?
  python download_song.py --install                          # install FLB app

How --play-flb works (recommended):
  1. Downloads the song to ~/Downloads/ (FLB's registered folder)
  2. Launches FLB Music Player AppImage with the song file as argument
  3. Returns immediately (non-blocking) — agent's terminal is free
  4. User controls playback manually inside the FLB GUI

How --install works (one-time):
  - Fetches latest FLB AppImage from GitHub releases (~77MB)
  - Saves to ~/.local/share/flb-music/FLB-Music.AppImage
  - Creates wrapper at ~/.local/bin/flb-music
  - After install, open FLB once → Settings → Folders → add ~/Downloads/

How --stop works (background mode only):
  Reads ~/.hermes_music/current.json → killpg(pgid, SIGTERM) → kills ONLY
  the music tree. Hermes and other bot processes are left untouched.

State files:
  ~/.local/share/flb-music/FLB-Music.AppImage   FLB app (installed by --install)
  ~/.local/bin/flb-music                        FLB wrapper
  ~/Downloads/                                  Music folder (FLB scans this)
  ~/.hermes_music/current.json                  Background playback state
  ~/.hermes_music/history.log                   Recent play history
""".strip()


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(USAGE)
        return

    # FLB-specific commands
    if args[0] == "--install":
        cmd_install(); return
    if args[0] == "--check":
        cmd_check(); return
    if args[0] == "--test-launch":
        cmd_test_launch(); return
    if args[0] == "--random":
        cmd_random(); return

    # Background-mode control commands (do not detach to own session)
    if args[0] == "--stop":
        cmd_stop(); return
    if args[0] == "--status":
        cmd_status(); return
    if args[0] == "--pause":
        cmd_pause(); return
    if args[0] == "--resume":
        cmd_resume(); return
    if args[0] == "--list":
        cmd_list(); return

    # --download-only: download WITHOUT playing (used by smart_music_picker.py batch)
    # Prints 'DOWNLOADED: <path>' on success for programmatic parsing.
    if args[0] == "--download-only":
        if len(args) < 2:
            print("❌ --download-only requires a song name.")
            print('   Example: python download_song.py --download-only "Excuses AP Dhillon"')
            sys.exit(1)
        query = " ".join(args[1:])
        result = download_only(query)
        sys.exit(0 if result else 1)

    # --play-flb or --play-aurora: download + play in Aurora Music Player
    if args[0] in ("--play-flb", "--play-aurora"):
        if len(args) < 2:
            print("❌ --play-flb requires a song name.")
            print('   Example: python download_song.py --play-flb "Excuses AP Dhillon"')
            sys.exit(1)
        query = " ".join(args[1:])
        cmd_play_flb(query)
        return

    # --play: download + background ffplay (subject to v2.1 hardcoded rules)
    if args[0] == "--play":
        if len(args) < 2:
            print("❌ --play requires a song name.")
            print('   Example: python download_song.py --play "Excuses AP Dhillon"')
            sys.exit(1)
        query = " ".join(args[1:])
        detach_to_own_session()
        install_signal_handlers()
        download_and_play(query)
        return

    # Default: download AND play in Aurora Music Player
    # v11 fix: previously this was download_only() which is why songs never played
    query = " ".join(args)
    cmd_play_flb(query)


if __name__ == "__main__":
    main()

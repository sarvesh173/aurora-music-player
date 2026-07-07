#!/usr/bin/env python3
"""
Aurora Music Player v8.0 — Ultimate Edition
============================================
Custom-built from scratch. No FLB/Alger copy-paste.
PySide6 + Qt Multimedia + MPRIS + Lucide-style SVG icons.

Features (20+):
1.  Custom SVG icons (no emojis, no Qt standard icons)
2.  Glassmorphism panels (rgba, blur simulation)
3.  Metallic gradient play button
4.  Smooth QPropertyAnimation page transitions
5.  Loading spinner during library scan
6.  Album art with rounded corners
7.  Now-playing highlight with color transition
8.  Hover glow on control buttons
9.  Gradient seek bar
10. Search with live filter
11. Sort by date/title/artist/album
12. Playlist creation + persistence
13. Queue management (add next/last)
14. Repeat (off/all/one) + shuffle
15. System tray icon
16. Keyboard shortcuts
17. Settings persistence (JSON)
18. MPRIS DBus (playerctl native)
19. CLI args for agent (--play-file etc)
20. Single-instance lock + IPC
21. Auto-rescan every 10 min + manual Refresh button (v14; F5 shortcut)
22. Context menu on songs
23. Window state save/restore
24. Responsive layout
25. Material 3 design system (v12.3) — full M3 dark color scheme (seed
    #6366F1), color roles named after Compose MaterialTheme.colorScheme,
    M3 type scale, shape scale (FAB play button, pill nav items, search
    bar), and 8%/12% state layers — translated from the Android Material 3
    spec to Qt Style Sheets. See skill/MATERIAL3_PROMPT.md.
26. v13.0 "Fancy" visual engine (reverse-engineered from FLB Music Player's
    Vue/Electron UI, re-implemented natively in Qt — zero web runtime):
    - Full-window blurred album-art backdrop with dark gradient scrim
      (FLB bg.vue equivalent; cheap box-blur via 24px downscale+upscale,
      precomputed per track + per resize, so Celeron-class CPUs stay idle)
    - Glassy translucent sidebar / player bar over the backdrop
    - Rich track rows via QStyledItemDelegate: 48px rounded album-art
      thumbnail (lazy-built, LRU-cached), 2-line title/artist, right
      duration, accent pill indicator on the playing track (FLB track-card)
27. Pop/click-free track switching (v13.0): stop -> swap source -> play with
    a ~120ms volume fade-in ramp; perceptual (logarithmic) volume curve.
28. v15.0 PLAYLISTS THAT WORK: open a playlist (double-click) into a detail
    page with rich track rows; add songs from a multi-select picker or the
    library right-click menu; remove/reorder songs; rename/delete/play the
    whole playlist. Playlists persist in ~/.aurora-player/playlists.json.
29. v15.0 QUEUE THAT WORKS: remove (right-click or Delete key), move up/down,
    clear, save queue as playlist, double-click to jump-play. Rich rows.
30. v15.0 Settings page: THEME COLOR SLIDER — drag a hue slider (0-359) and
    the entire Material 3 palette (all tonal roles) regenerates live from
    that seed hue. Also: beat-graph toggle, audio device, library info.
31. v15.0 Beat graph visualizer (SoundCloud-style motion graphics): real
    per-track peak levels via QAudioDecoder (async, no extra deps), bars
    bounce with the beat near the playhead, travelling shimmer wave, pulsing
    playhead glow. Click/drag the graph to seek. 30fps only while playing;
    pure QPainter — Celeron-friendly. Pseudo-waveform fallback for codecs
    that can't be decoded.
32. v15.0 agent upgrades: --new-playlist, --add-to-playlist, --play-playlist,
    --list-playlists, --queue-file, --queue-next-file, --queue-remove,
    --queue-clear, --set-theme. Richer --status JSON (queue + playlists).
33. v15.0 bug fixes: click-to-jump on seek/volume sliders (ClickSlider),
    working mute button, dancing-EQ badge on the playing row, queue page
    kept in sync while tracks auto-advance.
"""

import sys, os, json, shutil, subprocess, re
from pathlib import Path
from enum import Enum
from datetime import datetime

try:
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QSlider, QLabel, QListWidget, QListWidgetItem, QFrame, QStackedWidget,
        QLineEdit, QComboBox, QMenu, QSystemTrayIcon, QInputDialog, QSizePolicy, QDialog,
        QStyledItemDelegate, QStyle, QScrollArea, QAbstractItemView, QDialogButtonBox,
        QProgressBar, QToolButton, QGridLayout, QSpacerItem, QSpinBox, QCheckBox)
    from PySide6.QtCore import (Qt, QUrl, QTimer, QThread, Signal, QSize, QPropertyAnimation,
        QEasingCurve, QByteArray, QParallelAnimationGroup, QSequentialAnimationGroup,
        QRectF, QRect, QObject, QPoint, QMutex, QReadWriteLock, Property)
    from PySide6.QtGui import (QIcon, QFont, QPixmap, QColor, QPalette, QAction, QImage,
        QPainter, QLinearGradient, QBrush, QPen, QPainterPath, QFontMetrics)
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices, QAudioBufferOutput, QAudioFormat
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
except ImportError:
    print("ERROR: pip install PySide6 --break-system-packages"); sys.exit(1)

try:
    from mutagen import File as MutagenFile
    from mutagen.mp3 import MP3; from mutagen.flac import FLAC; from mutagen.mp4 import MP4
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

try:
    from mpris_server.server import Server
    from mpris_server.adapters import MprisAdapter
    from mpris_server.base import PlayState, Track
    HAS_MPRIS = True
except ImportError:
    HAS_MPRIS = False; PlayState = None; Track = None

# ===== Constants =====
APP_NAME = "Aurora Music Player"
APP_VERSION = "17.5.0"
APP_DBUS = "aurora"
MUSIC_FOLDER = Path.home() / "Downloads"

# ===== v16: Browse (online search + suggestions + preview + 1-click download) ====
# iTunes Search API: free, no API key, ~20 req/min, returns 30-sec previewUrl +
# artworkUrl100 + full metadata (title, artist, album, genre, duration).
# We swap the 100x100 thumbnail URL up to 600x600 for the grid, and the
# previewUrl (.m4a) is directly playable by QMediaPlayer + downloadable.
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"
ITUNES_MEDIA = "music"
ITUNES_ENTITY = "song"
BROWSE_RESULT_LIMIT = 50        # v16.5: page size — infinite scroll fetches more
BROWSE_SUGGEST_LIMIT = 8
BROWSE_DEBOUNCE_MS = 250  # iTunes is fast (~120ms) but we still debounce keystrokes
BROWSE_THUMB_SIZE = 96    # Browse grid thumbnail size (px)
# v16.5: scroll-position threshold (px from bottom) that triggers next page load
BROWSE_INFINITE_SCROLL_THRESHOLD = 400
# v16.5: hard cap on infinite scroll (safety — iTunes allows up to 200 per query)
BROWSE_MAX_TOTAL_RESULTS = 200

# v16.7: Country-specific seed queries — shown on first Browse visit when the
# search field is empty. Each country gets seeds that are relevant to its
# storefront, so country=IN shows Bollywood/Punjabi/Tamil content (not Taylor
# Swift). iTunes' `country` parameter only affects availability, not the search
# algorithm — so we MUST use region-specific search terms to get regional content.
BROWSE_SEED_QUERIES = {
    "IN": ["bollywood hits 2024", "punjabi songs", "tamil hits", "telugu hits",
           "arijit singh", "hindi songs", "indian pop", "bollywood romantic"],
    "US": ["top hits 2024", "taylor swift", "pop hits", "hip hop hits",
           "ed sheeran", "billie eilish", "drake", "lofi beats"],
    "GB": ["uk top charts", "adele", "ed sheeran", "sam smith",
           "uk rap", "britpop", "dua lipa", "stormzy"],
    "CA": ["canadian hits", "the weeknd", "drake", "justin bieber",
           "shawn mendes", "canadian pop", "canadian rap"],
    "AU": ["australian hits", "tame impala", "acdc", "kylie minogue",
           "australian pop", "triple j hits"],
    "DE": ["deutsche hits", "deutschpop", "rammstein", "helene fischer",
           "german rap", "schlager"],
    "FR": ["chansons francaises", "french rap", "daft punk", "stromae",
           "indila", "french pop"],
    "JP": ["jpop hits", "anime songs", "yoasobi", "kenshi yonezu",
           "japanese rock", "vocaloid"],
}
# Default seeds for countries not in the map above
BROWSE_SEED_QUERIES_DEFAULT = ["top hits 2024", "pop hits", "lofi beats",
                                "acoustic covers", "workout mix"]

# ===== v16.6: YouTube bot-protection bypass (multi-strategy) ====
# Strategy order (tried in sequence until one works):
#   1. cookies-from-browser (auto-detect installed browser)
#   2. cookies.txt file (Netscape format, user-provided)
#   3. client-type rotation (yt-dlp --extractor-args with multiple player_clients)
#   4. Invidious API fallback (3 instances, audio URL extraction)
#   5. SAPISIDHASH Innertube direct /youtubei/v1/player API call
#   6. Plain yt-dlp (last resort — works for non-bot-protected videos)
# Reference: JustAnotherMusicClient's 5-client-type matrix in lib.rs lines 1518-1648
# and tauriFetch.ts SAPISIDHASH computation (lines 92-128).

# Browsers yt-dlp --cookies-from-browser supports (auto-detection order)
YTDLP_BROWSER_CHOICES = ["firefox", "chrome", "chromium", "brave", "edge",
                         "opera", "safari", "vivaldi", "whale"]

# Invidious instances (from youtube-music-cli/api.ts lines 1043-1047)
INVIDIOUS_INSTANCES = [
    "https://vid.puffyan.us",
    "https://invidious.perennialte.ch",
    "https://yewtu.be",
]

# Client-type rotation for yt-dlp (from JustAnotherMusicClient lib.rs lines 1518-1532)
# Order: mobile-first (less likely to trigger bot detection)
YTDLP_PLAYER_CLIENTS = "ios,android,tv,web,web_safari"

# Hardcoded Innertube API key (public, same as JustAnotherMusicClient lib.rs line 58)
INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
INNERTUBE_PLAYER_URL = "https://www.youtube.com/youtubei/v1/player"
INNERTUBE_MUSIC_PLAYER_URL = "https://music.youtube.com/youtubei/v1/player"

# 5-client-type contexts (copied from JustAnotherMusicClient lib.rs lines 1571-1648)
# Each entry: (client_name_str, client_version, user_agent, x_youtube_client_name)
INNERTUBE_CLIENTS = [
    ("ios",       "20.11.6",         "com.google.ios.youtube/20.11.6 (iPhone10,4; U; CPU iOS 16_7_7 like Mac OS X)", "5"),
    ("android",   "21.03.36",        "com.google.android.youtube/21.03.36(Linux; U; Android 16; en_US; SM-S908E Build/TP1A.220624.014) gzip", "3"),
    ("tv",        "7.20260311.12.00","Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version", "7"),
    ("web",       "2.20260206.01.00","Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36", "1"),
    ("web_remix", "1.20250506.00.00","Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36", "67"),
]
CONFIG_DIR = Path.home() / ".aurora-player"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "settings.json"
PID_FILE = CONFIG_DIR / "pid.lock"
PLAYLISTS_FILE = CONFIG_DIR / "playlists.json"
STATUS_FILE = CONFIG_DIR / "status.json"
# v16.8: History persistence — last 100 played songs with metadata
# (date, exact time, play count, session info). FIFO eviction when > 100.
HISTORY_FILE = CONFIG_DIR / "history.json"
HISTORY_MAX_ENTRIES = 100
# v16.8: Session time tracking — stored cumulatively across sessions
SESSION_FILE = CONFIG_DIR / "session.json"
# v17.0: Equalizer + repeat/skip stats persistence
EQUALIZER_FILE = CONFIG_DIR / "equalizer.json"
REPEAT_STATS_FILE = CONFIG_DIR / "repeat_stats.json"

# v17.0: 10-band equalizer frequency centers (Hz) — standard ISO 1/3 octave
EQ_BANDS_HZ = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
EQ_BAND_LABELS = ["31", "62", "125", "250", "500", "1K", "2K", "4K", "8K", "16K"]
EQ_BANDS_COUNT = len(EQ_BANDS_HZ)
# Gain range in dB (-12 to +12, 0 = flat)
EQ_MIN_GAIN = -12
EQ_MAX_GAIN = 12
EQ_DEFAULT_GAIN = 0

# v17.0: Built-in EQ presets (gain in dB for each of the 10 bands)
EQ_PRESETS = {
    "Flat":        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "Bass Boost":  [8, 6, 4, 2, 0, 0, 0, 0, 0, 0],
    "Treble Boost":[0, 0, 0, 0, 0, 0, 2, 4, 6, 8],
    "Vocal":       [-2, -2, 0, 2, 4, 4, 3, 1, 0, -1],
    "Rock":        [4, 3, 0, -1, -2, 0, 2, 3, 4, 4],
    "Pop":         [-1, 1, 3, 3, 1, 0, -1, -1, 1, 2],
    "Jazz":        [3, 2, 1, 0, -1, -1, 0, 1, 2, 3],
    "Classical":   [4, 3, 2, 0, -1, -1, 0, 2, 3, 4],
    "Electronic":  [5, 4, 1, 0, -2, 2, 1, 1, 4, 5],
    "Loudness":    [6, 4, 0, 0, -2, 0, 0, 2, 4, 6],
}

SUPPORTED = {".mp3", ".m4a", ".flac", ".ogg", ".wav", ".opus", ".aac", ".wma"}

# ===== v17.3: Visualizer modes (inspired by CAVA + Kurve) =====
# The user can change the graph type in Settings → Visualizer card.
# Modes: 0=Beat Graph (existing), 1=Bars, 2=Mirror Bars, 3=Wave, 4=Radial Bars, 5=Blocks
VIZ_MODES = ["Beat Graph", "Bars", "Mirror Bars", "Wave", "Radial Bars", "Blocks"]
VIZ_DEFAULT_MODE = 0
VIZ_FILE = CONFIG_DIR / "visualizer.json"

def load_viz_config():
    """v17.3: Load visualizer config from disk."""
    default = {"mode": VIZ_DEFAULT_MODE, "bar_width": 4, "bar_gap": 2,
               "smoothing": 77, "rounded": True}
    if VIZ_FILE.exists():
        try:
            d = json.loads(VIZ_FILE.read_text())
            for k in default:
                if k not in d: d[k] = default[k]
            return d
        except Exception: pass
    return default

def save_viz_config(cfg):
    """v17.3: Save visualizer config."""
    try: VIZ_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception: pass

# ===== Material 3 Design Tokens (v12.3) =====
# Material 3 color roles — dark scheme generated from seed #6366F1 (Aurora indigo).
# Naming mirrors Jetpack Compose MaterialTheme.colorScheme
# (developer.android.com/develop/ui/compose/designsystems/material3), translated
# to Qt Style Sheets. See skill/MATERIAL3_PROMPT.md for the full mapping.
DEFAULT_HUE = 239  # hue of seed #6366F1 (Aurora indigo)
DEFAULT_M3 = {
    # Primary group (tonal palette of seed #6366F1)
    "primary":                  "#BFC2FF",  # P-80
    "on_primary":               "#252478",  # P-20
    "primary_container":        "#3D3C8F",  # P-30
    "on_primary_container":     "#E0E0FF",  # P-90
    # Secondary group
    "secondary":                "#C5C4DD",
    "on_secondary":             "#2E2F42",
    "secondary_container":      "#444559",
    "on_secondary_container":   "#E1E0F9",
    # Tertiary group
    "tertiary":                 "#E8B9D5",
    "on_tertiary":              "#46263B",
    "tertiary_container":       "#5F3C52",
    "on_tertiary_container":    "#FFD8EC",
    # Error group
    "error":                    "#FFB4AB",
    "on_error":                 "#690005",
    "error_container":          "#93000A",
    "on_error_container":       "#FFDAD6",
    # Surface group (M3 dark tonal surfaces)
    "surface":                  "#131318",
    "surface_dim":              "#131318",
    "surface_bright":           "#39383F",
    "surface_container_lowest": "#0D0E13",
    "surface_container_low":    "#1B1B21",
    "surface_container":        "#1F1F25",
    "surface_container_high":   "#292A2F",
    "surface_container_highest":"#34343A",
    "on_surface":               "#E4E1E9",
    "on_surface_variant":       "#C7C5D0",
    "outline":                  "#918F9A",
    "outline_variant":          "#46464F",
    "inverse_surface":          "#E4E1E9",
    "inverse_on_surface":       "#303036",
    "inverse_primary":          "#5456C9",
}

def _rgba(hex_color, alpha):
    """hex -> 'rgba(r,g,b,a)' for QSS state layers."""
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{alpha})"

def _mix(base, layer, t):
    """Blend `layer` over `base` at opacity t — precomputed M3 state layer."""
    b = base.lstrip("#"); l = layer.lstrip("#")
    c = [round(int(b[i:i+2],16)*(1-t) + int(l[i:i+2],16)*t) for i in (0,2,4)]
    return "#{:02X}{:02X}{:02X}".format(*c)

def _hsl(h, s, l):
    """hue 0-360, saturation 0-1, lightness 0-100 -> #RRGGBB"""
    import colorsys
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l / 100.0, s)
    return "#{:02X}{:02X}{:02X}".format(round(r*255), round(g*255), round(b*255))

def make_m3(hue):
    """v15: generate a full M3 dark palette from a seed hue (0-359).
    Tone/chroma values approximate the Material 3 dark-scheme tonal mapping
    (primary=P80, container=P30, hue-tinted neutral surfaces, tertiary=hue+60)."""
    h = int(hue) % 360; h2 = (h + 60) % 360
    return {
        "primary": _hsl(h,0.90,84), "on_primary": _hsl(h,0.55,26),
        "primary_container": _hsl(h,0.42,36), "on_primary_container": _hsl(h,0.92,91),
        "secondary": _hsl(h,0.26,82), "on_secondary": _hsl(h,0.19,23),
        "secondary_container": _hsl(h,0.15,28), "on_secondary_container": _hsl(h,0.30,90),
        "tertiary": _hsl(h2,0.45,80), "on_tertiary": _hsl(h2,0.30,22),
        "tertiary_container": _hsl(h2,0.24,31), "on_tertiary_container": _hsl(h2,0.60,92),
        "error": "#FFB4AB", "on_error": "#690005",
        "error_container": "#93000A", "on_error_container": "#FFDAD6",
        "surface": _hsl(h,0.10,8), "surface_dim": _hsl(h,0.10,8), "surface_bright": _hsl(h,0.06,23),
        "surface_container_lowest": _hsl(h,0.12,5), "surface_container_low": _hsl(h,0.09,11),
        "surface_container": _hsl(h,0.08,12), "surface_container_high": _hsl(h,0.07,17),
        "surface_container_highest": _hsl(h,0.06,21),
        "on_surface": _hsl(h,0.08,90), "on_surface_variant": _hsl(h,0.10,79),
        "outline": _hsl(h,0.05,58), "outline_variant": _hsl(h,0.07,29),
        "inverse_surface": _hsl(h,0.08,90), "inverse_on_surface": _hsl(h,0.06,19),
        "inverse_primary": _hsl(h,0.50,56),
    }

# The live palette. Mutated IN PLACE by apply_theme_hue() so every painter
# (delegates, backdrop, visualizer) that reads M3[...] re-themes automatically.
M3 = dict(DEFAULT_M3)

def _finish_m3():
    # M3 state layers: hover = 8%, press = 12% of the content color over container
    M3["state_hover_on_surface"]   = _rgba(M3["on_surface"], 0.08)
    M3["state_press_on_surface"]   = _rgba(M3["on_surface"], 0.12)
    M3["primary_hover"]            = _mix(M3["primary"], M3["on_primary"], 0.08)
    M3["primary_press"]            = _mix(M3["primary"], M3["on_primary"], 0.12)
    M3["primary_container_hover"]  = _mix(M3["primary_container"], M3["on_primary_container"], 0.08)
    M3["primary_container_press"]  = _mix(M3["primary_container"], M3["on_primary_container"], 0.12)
    M3["secondary_container_hover"] = _mix(M3["secondary_container"], M3["on_secondary_container"], 0.08)

def apply_theme_hue(hue):
    """v15: retheme the whole app from one hue. DEFAULT_HUE keeps the
    hand-tuned indigo palette; anything else is generated by make_m3()."""
    pal = DEFAULT_M3 if abs(int(hue) - DEFAULT_HUE) <= 1 else make_m3(hue)
    M3.clear(); M3.update(pal); _finish_m3()

_finish_m3()

# ===== SVG Icons (Material Symbols paths — single-path, clean) =====
def _svg(path_data, fill=None, size=24):
    fill = fill or M3["on_surface_variant"]
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{fill}" width="{size}" height="{size}"><path d="{path_data}"/></svg>'
    r = QSvgRenderer(svg.encode())
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); r.render(p); p.end()
    return QIcon(pm)

IC_PLAY = "M8 5v14l11-7z"
IC_PAUSE = "M6 19h4V5H6v14zm8-14v14h4V5h-4z"
IC_NEXT = "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"
IC_PREV = "M6 6h2v12H6zm3.5 6l8.5 6V6z"
IC_SHUFFLE = "M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"
IC_REPEAT = "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"
IC_REPEAT1 = "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4zm-4-1v-6h-1l-2 1v1h1.5v4H13z"
IC_VOL = "M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"
IC_SEARCH = "M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14z"
IC_MUSIC = "M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"
IC_LIST = "M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"
IC_PLUS = "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"
IC_TRASH = "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"
IC_HEART = "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
IC_SETTINGS = "M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"
IC_REFRESH = "M17.65 6.35A7.95 7.95 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"
IC_AUDIO_DEVICE = "M12 2a10 10 0 0 1 10 10A10 10 0 0 1 2 12 10 10 0 0 1 12 2zm0 2.5a7.5 7.5 0 0 0 0 15 7.5 7.5 0 0 0 0-15zm6.5 1.5h-5a1 1 0 0 1 0-2h5a1 1 0 0 1 0 2zm-8-2h5a1 1 0 0 1 0 2h-5a1 1 0 0 1 0-2zm8 8H5a1 1 0 0 1 0-2h10a1 1 0 0 1 0 2z"
# v15 icons (Material Symbols)
IC_MUTE = "M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"
IC_PLAYLIST_ADD = "M14 10H2v2h12v-2zm0-4H2v2h12V6zm4 8v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zM2 16h8v-2H2v2z"
IC_PLAYLIST_PLAY = "M19 9H2v2h17V9zm0-4H2v2h17V5zM2 15h13v-2H2v2zm15-2v6l5-3-5-3z"
IC_CLOSE = "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"
IC_UP = "M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.58L20 12l-8-8-8 8z"
IC_DOWN = "M20 12l-1.41-1.41L13 16.17V4h-2v12.17l-5.58-5.59L4 12l8 8 8-8z"
IC_BACK = "M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"
IC_PALETTE = "M12 3c-4.97 0-9 4.03-9 9s4.03 9 9 9c.83 0 1.5-.67 1.5-1.5 0-.39-.15-.74-.39-1.01-.23-.26-.38-.61-.38-.99 0-.83.67-1.5 1.5-1.5H16c2.76 0 5-2.24 5-5 0-4.42-4.03-8-9-8zm-5.5 9c-.83 0-1.5-.67-1.5-1.5S5.67 9 6.5 9 8 9.67 8 10.5 7.33 12 6.5 12zm3-4C8.67 8 8 7.33 8 6.5S8.67 5 9.5 5s1.5.67 1.5 1.5S10.33 8 9.5 8zm5 0c-.83 0-1.5-.67-1.5-1.5S13.67 5 14.5 5s1.5.67 1.5 1.5S15.33 8 14.5 8zm3 4c-.83 0-1.5-.67-1.5-1.5S16.67 9 17.5 9s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"
IC_EQ = "M7 18h2V6H7v12zm4 4h2V2h-2v20zm-8-8h2v-4H3v4zm12 4h2V6h-2v12zm4-8v4h2v-4h-2z"
IC_CHECK = "M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"
IC_EDIT = "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34a.9959.9959 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"
# v16 icons (Material Symbols) — Browse feature
IC_DOWNLOAD = "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"
IC_BROWSE = "M12 10.9c-.61 0-1.1.49-1.1 1.1s.49 1.1 1.1 1.1c.61 0 1.1-.49 1.1-1.1s-.49-1.1-1.1-1.1zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm2.19 12.19L6 18l3.81-8.19L18 6l-3.81 8.19z"
IC_EXPLORE = "M12 10.9c-.61 0-1.1.49-1.1 1.1s.49 1.1 1.1 1.1c.61 0 1.1-.49 1.1-1.1s-.49-1.1-1.1-1.1zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm2.19 12.19L6 18l3.81-8.19L18 6l-3.81 8.19z"
IC_CLOUD = "M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z"
IC_STAR = "M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"
IC_PREVIEW = "M12 3v9.28c-.47-.17-.97-.28-1.5-.28C8.01 12 6 14.01 6 16.5S8.01 21 10.5 21s4.5-2.01 4.5-4.5c0-.17-.02-.33-.05-.49H15V6h4V3h-7z"
IC_QUEUE_DOWNLOAD = "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"
IC_LOADING = "M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"
IC_OPEN_EXTERNAL = "M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"
# v16.8 icons — History feature + help command
IC_HISTORY = "M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z"
IC_TIMER = "M15 1H9v2h6V1zm-4 13h2V8h-2v6zm8.03-6.61 1.42-1.42c-.43-.51-.9-.99-1.41-1.41l-1.42 1.42A8.962 8.962 0 0 0 12 4a9 9 0 1 0 9 9c0-2.12-.74-4.07-1.97-5.61zM12 20c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"
IC_HELP = "M11 18h2v-2h-2v2zm1-16C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-14c-2.21 0-4 1.79-4 4h2c0-1.1.9-2 2-2s2 .9 2 2c0 2-3 1.75-3 5h2c0-2.25 3-2.5 3-5 0-2.21-1.79-4-4-4z"
IC_STATS = "M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"
IC_REPEAT_COUNT = "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"
# v17.0 icons — Equalizer + animations + repeat info
IC_EQUALIZER = "M10 20h4V4h-4v16zm-6 0h4v-8H4v8zm12 0h4v-4h-4v4z"
IC_FORWARD_SKIP = "M4 5v14l8-7-8-7zm9 0v14l8-7-8-7z"
IC_BACKWARD_SKIP = "M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z"
IC_PULSE = "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16zm-.5-13h-1v6l5.2 3.2.6-1-4.8-2.8V7z"
# v17.1 icons — custom SVG icons from Material Design Icons (Templarian/MaterialDesign)
# Source: https://github.com/Templarian/MaterialDesign — viewBox="0 0 24 24"
# These replace ALL emojis in the app (📅 🔁 ⏭ ⏮ → proper SVG icons)
IC_CALENDAR = "M19,19H5V8H19M16,1V3H8V1H6V3H5C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5C21,3.89 20.1,3 19,3H18V1M17,12H12V17H17V12Z"
IC_REPEAT_COUNT_ICON = "M13,15V9H12L10,10V11H11.5V15M17,17H7V14L3,18L7,22V19H19V13H17M7,7H17V10L21,6L17,2V5H5V11H7V7Z"
IC_SKIP_FWD = "M16,18H18V6H16M6,18L14.5,12L6,6V18Z"
IC_SKIP_BWD = "M6,18V6H8V18H6M9.5,12L18,6V18L9.5,12Z"
IC_CLOCK = "M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"
IC_BAR_CHART = "M22,21H2V3H4V19H6V10H10V19H12V6H16V19H18V14H22V21Z"
IC_PLAY_CIRCLE = "M10,16.5V7.5L16,12M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z"
IC_HISTOGRAM = "M3,3H5V13H9V7H13V11H17V15H21V21H3V3Z"

# ===== v14.0: ElideLabel — text shrinks with "..." instead of pushing the
# layout around. This is what fixes the button glitches on window resize:
# long titles used to force the controls to squeeze/overlap. (Pattern learned
# from Harmonoid's desktop now-playing bar: fixed controls + elided text.)
class ElideLabel(QLabel):
    def __init__(self, text="", *a, **k):
        super().__init__(text, *a, **k); self._full = text
    def setText(self, t):
        self._full = t; self._elide()
    def resizeEvent(self, e):
        super().resizeEvent(e); self._elide()
    def _elide(self):
        fm = self.fontMetrics()
        super().setText(fm.elidedText(getattr(self, "_full", ""), Qt.ElideRight, max(30, self.width() - 4)))

# ===== v15: ClickSlider — click anywhere on the groove to jump there =====
# (old sliders only responded to dragging the handle; clicking did nothing)
class ClickSlider(QSlider):
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.maximum() > self.minimum():
            v = self.minimum() + (self.maximum() - self.minimum()) * e.position().x() / max(1, self.width())
            self.setValue(int(v)); self.sliderMoved.emit(int(v))
        super().mousePressEvent(e)

# ===== v17.3: AnimatedButton — press-scale animation on ALL control buttons =====
# Inspired by Material Design 3 ripple + scale interaction.
# When pressed, the button shrinks to 90% then bounces back to 100% in ~150ms.
class AnimatedButton(QPushButton):
    """v17.3: QPushButton with press-scale animation. Uses QPropertyAnimation
    on a custom _scale property to create a bouncy press effect."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scale = 1.0
        self._anim = None
    def _get_scale(self): return self._scale
    def _set_scale(self, v):
        self._scale = v
        self.update()
    scale = Property(float, _get_scale, _set_scale)
    def mousePressEvent(self, e):
        # Animate: shrink to 0.88 then bounce back to 1.0
        if self._anim: self._anim.stop()
        self._anim = QSequentialAnimationGroup(self)
        shrink = QPropertyAnimation(self, b"scale", self)
        shrink.setDuration(80); shrink.setStartValue(1.0); shrink.setEndValue(0.88)
        bounce = QPropertyAnimation(self, b"scale", self)
        bounce.setDuration(120); bounce.setStartValue(0.88); bounce.setEndValue(1.0)
        bounce.setEasingCurve(QEasingCurve.OutBack)
        self._anim.addAnimation(shrink); self._anim.addAnimation(bounce)
        self._anim.start()
        super().mousePressEvent(e)
    def enterEvent(self, e):
        # Subtle grow on hover (1.0 → 1.05)
        if self._anim: self._anim.stop()
        self._anim = QPropertyAnimation(self, b"scale", self)
        self._anim.setDuration(100); self._anim.setStartValue(self._scale)
        self._anim.setEndValue(1.05); self._anim.start()
        super().enterEvent(e)
    def leaveEvent(self, e):
        # Shrink back to 1.0
        if self._anim: self._anim.stop()
        self._anim = QPropertyAnimation(self, b"scale", self)
        self._anim.setDuration(100); self._anim.setStartValue(self._scale)
        self._anim.setEndValue(1.0); self._anim.start()
        super().leaveEvent(e)

# ===== v15: LevelScanner — async per-track peak levels for the visualizer ====
# Uses QAudioDecoder (Qt's bundled ffmpeg backend): no extra dependency, fully
# async on the Qt event loop, one ~26ms peak level per decoded buffer.
# NOTE: do NOT set a custom QAudioFormat — the ffmpeg backend stalls when
# asked to resample; reading the native format works everywhere.
class LevelScanner(QObject):
    done = Signal(str, list)
    def __init__(self, parent=None):
        super().__init__(parent); self.dec = None; self.path = None; self.levels = []
    def scan(self, path):
        self.cancel()
        self.path = path; self.levels = []
        try:
            from PySide6.QtMultimedia import QAudioDecoder
            self.dec = QAudioDecoder(self)
            self.dec.setSource(QUrl.fromLocalFile(path))
            self.dec.bufferReady.connect(self._ready)
            self.dec.finished.connect(self._fin)
            self.dec.error.connect(lambda *_: self._fin())
            self.dec.start()
        except Exception as e:
            print(f"[Aurora] LevelScanner unavailable: {e}", flush=True)
            self.dec = None; self.done.emit(path, [])
    def cancel(self):
        if self.dec is not None:
            try:
                self.dec.blockSignals(True); self.dec.stop()
            except Exception: pass
            self.dec.deleteLater(); self.dec = None
    def _ready(self):
        if self.dec is None: return
        try:
            from array import array
            from PySide6.QtMultimedia import QAudioFormat
            buf = self.dec.read()
            if not buf.isValid(): return
            sf = buf.format().sampleFormat(); data = bytes(buf.data())
            if sf == QAudioFormat.SampleFormat.Float:
                arr = array('f', data[:len(data)//4*4]); div = 1.0
            elif sf == QAudioFormat.SampleFormat.Int16:
                arr = array('h', data[:len(data)//2*2]); div = 32768.0
            elif sf == QAudioFormat.SampleFormat.Int32:
                arr = array('i', data[:len(data)//4*4]); div = 2147483648.0
            else:
                arr = array('B', data); div = None
            if not len(arr): return
            if div is None:
                lv = max(abs(x - 128) for x in arr[::8]) / 128.0
            else:
                lv = min(1.0, max(abs(x) for x in arr[::8]) / div)
            self.levels.append(lv)
        except Exception:
            pass
    def _fin(self):
        p = self.path; lv = self.levels
        self.cancel()
        if p: self.done.emit(p, lv)

def pseudo_levels(path, dur):
    """Deterministic fallback waveform (seeded random walk) so the beat graph
    still looks alive when a codec can't be decoded."""
    import random as _r
    rnd = _r.Random(hash(path) & 0xFFFFFFFF)
    n = max(80, min(600, int((dur or 180) * 2)))
    v = 0.5; out = []
    for _ in range(n):
        v = min(1.0, max(0.10, v + rnd.uniform(-0.16, 0.16)))
        out.append(v * (0.7 + 0.3 * rnd.random()))
    return out

# ===== v15: Visualizer — SoundCloud-style animated beat/waveform graph ======
# One bar per ~5px resampled from the track's real peak levels. Played part is
# primary-colored; bars near the playhead bounce with the actual beat and a
# shimmer wave travels through them (motion graphics). Click/drag = seek.
# Repaints at 30fps ONLY while playing; pure QPainter rects (no images) so a
# Celeron stays cool. Toggle in Settings.
class Visualizer(QWidget):
    BAR_W = 3; GAP = 2; PAD = 16
    def __init__(self, win):
        super().__init__(); self.win = win
        self.setFixedHeight(52); self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Beat graph — click to seek")
        self.levels = []; self.bars = []; self.real = False
        self._pulse = 0.0; self._phase = 0.0
        # v17.5: Real-time spectrum bars from QAudioBufferOutput (LIVE audio sync)
        self.live_spectrum = []  # list of 0.0-1.0 floats from real-time FFT
        self.use_live = False    # True when live_spectrum has data
        # v17.3: Visualizer mode (0=Beat Graph, 1=Bars, 2=Mirror, 3=Wave, 4=Radial, 5=Blocks)
        viz_cfg = load_viz_config()
        self.viz_mode = viz_cfg.get("mode", VIZ_DEFAULT_MODE)
        self.bar_w = viz_cfg.get("bar_width", 4)
        self.gap = viz_cfg.get("bar_gap", 2)
        self.rounded = viz_cfg.get("rounded", True)
        self.timer = QTimer(self); self.timer.setInterval(33); self.timer.timeout.connect(self._tick)
    def set_levels(self, levels, real):
        self.levels = levels or []; self.real = real
        self._resample(); self.update()
    def set_spectrum(self, bars):
        """v17.5: Receive REAL-TIME FFT spectrum bars from QAudioBufferOutput.
        bars = list of 0.0-1.0 floats (typically 32-64 bars).
        When this is called, the visualizer switches to live mode (synced to
        actual audio output) instead of pre-computed levels."""
        self.live_spectrum = list(bars) if bars else []
        self.use_live = len(self.live_spectrum) > 0
        # Also update _pulse from the live spectrum (average of first 8 bars = bass energy)
        if self.use_live:
            bass_energy = sum(self.live_spectrum[:8]) / max(1, len(self.live_spectrum[:8]))
            self._pulse += (bass_energy - self._pulse) * 0.50  # fast follow
        self.update()
    def set_playing(self, playing):
        if playing and self.isVisible(): self.timer.start()
        else: self.timer.stop(); self.update()
    def showEvent(self, e):
        super().showEvent(e)
        if self.win.playing: self.timer.start()
    def hideEvent(self, e):
        self.timer.stop(); super().hideEvent(e)
    def resizeEvent(self, e):
        self._resample(); super().resizeEvent(e)
    def _nbars(self):
        return max(16, (self.width() - 2*self.PAD) // (self.BAR_W + self.GAP))
    def _resample(self):
        n = self._nbars(); L = self.levels; self.bars = []
        if not L: return
        m = len(L); srt = sorted(L)
        ref = max(0.05, srt[int(0.95 * (m - 1))])  # normalize to 95th percentile
        for i in range(n):
            a = int(i * m / n); b = max(a + 1, int((i + 1) * m / n))
            self.bars.append(min(1.0, max(L[a:b]) / ref))
    def _ratio(self):
        d = self.win.player.duration()
        return (self.win.player.position() / d) if d > 0 else 0.0
    def _tick(self):
        """v17.4: SYNC FIX — pulse is computed from REAL audio levels at the
        playhead position, NOT a fake sine wave. The bars array contains the
        actual per-track peak levels (from QAudioDecoder via LevelScanner).
        bar[i] = real peak level at time (i/n * duration).
        When the playhead is at bar[i], that bar's value IS the actual audio
        level at that moment. We smooth it into _pulse so the animation
        literally follows the song's beat.

        The old code used `self._phase += 0.30` (a fake sine-wave) for the
        shimmer effect — that's been removed. ALL animation now derives from
        real audio data via _pulse (the smoothed amplitude at the playhead)."""
        if self.bars:
            # v17.4: Get the REAL audio level at the current playhead position
            playhead_idx = min(len(self.bars) - 1, int(self._ratio() * len(self.bars)))
            lv = self.bars[playhead_idx]
            # Also sample a few bars around the playhead for a "local energy" reading
            window_start = max(0, playhead_idx - 2)
            window_end = min(len(self.bars), playhead_idx + 3)
            local_energy = sum(self.bars[window_start:window_end]) / max(1, window_end - window_start)
            # Smooth into _pulse — this is the REAL beat pulse that drives all animation
            target_pulse = local_energy
            self._pulse += (target_pulse - self._pulse) * 0.40  # 40% smoothing per frame
        else:
            # No bars yet — flatline (no fake sine wave)
            self._pulse += (0.0 - self._pulse) * 0.3
        self.update()
    def _seek(self, x):
        d = self.win.player.duration()
        if d > 0:
            r = (x - self.PAD) / max(1, self.width() - 2*self.PAD)
            self.win.player.setPosition(int(d * min(1.0, max(0.0, r))))
    def mousePressEvent(self, e): self._seek(e.position().x())
    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton: self._seek(e.position().x())
    def paintEvent(self, e):
        import math
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height(); mid = h / 2
        # v17.5: If we have LIVE spectrum data (from QAudioBufferOutput), use it
        # for the non-beat-graph modes. Beat Graph (mode 0) still uses pre-computed
        # levels because it shows the whole-song waveform with a playhead.
        if self.use_live and self.viz_mode != 0:
            # LIVE mode — bars come from real-time FFT of actual audio output
            live_bars = self.live_spectrum
            n = len(live_bars)
            if n == 0:
                pen = QPen(QColor(M3["outline_variant"])); pen.setWidth(2); p.setPen(pen)
                p.drawLine(self.PAD, int(mid), w - self.PAD, int(mid)); p.end(); return
            playing = self.win.playing
            # Temporarily swap self.bars with live_spectrum for the paint methods
            orig_bars = self.bars
            self.bars = live_bars
            if self.viz_mode == 1:
                self._paint_bars(p, w, h, mid, n, playing, math, mirror=False)
            elif self.viz_mode == 2:
                self._paint_bars(p, w, h, mid, n, playing, math, mirror=True)
            elif self.viz_mode == 3:
                self._paint_wave(p, w, h, mid, n, playing, math)
            elif self.viz_mode == 4:
                self._paint_radial(p, w, h, mid, n, playing, math)
            elif self.viz_mode == 5:
                self._paint_blocks(p, w, h, mid, n, playing, math)
            self.bars = orig_bars  # restore
            p.end(); return
        # Pre-computed mode (beat graph or fallback when no live data)
        if not self.bars:
            pen = QPen(QColor(M3["outline_variant"])); pen.setWidth(2); p.setPen(pen)
            p.drawLine(self.PAD, int(mid), w - self.PAD, int(mid)); p.end(); return
        n = len(self.bars); r = self._ratio(); play_i = r * n
        playing = self.win.playing
        # v17.3: Dispatch to the correct mode renderer
        if self.viz_mode == 0:
            self._paint_beat_graph(p, w, h, mid, n, r, play_i, playing, math)
        elif self.viz_mode == 1:
            self._paint_bars(p, w, h, mid, n, playing, math, mirror=False)
        elif self.viz_mode == 2:
            self._paint_bars(p, w, h, mid, n, playing, math, mirror=True)
        elif self.viz_mode == 3:
            self._paint_wave(p, w, h, mid, n, playing, math)
        elif self.viz_mode == 4:
            self._paint_radial(p, w, h, mid, n, playing, math)
        elif self.viz_mode == 5:
            self._paint_blocks(p, w, h, mid, n, playing, math)
        else:
            self._paint_beat_graph(p, w, h, mid, n, r, play_i, playing, math)
        p.end()

    # ===== v17.3: Mode 0 — Beat Graph (existing, default) =====
    def _paint_beat_graph(self, p, w, h, mid, n, r, play_i, playing, math):
        p.setPen(Qt.NoPen)
        for i, lv in enumerate(self.bars):
            x = self.PAD + i * (self.BAR_W + self.GAP)
            amp = lv
            if playing:
                d = abs(i - play_i)
                if d < 10:
                    # v17.4: SYNC FIX — pulse is REAL (from audio levels), no fake sine
                    amp = min(1.0, lv * (1.0 + 0.55 * self._pulse * math.exp(-d*d/18.0)))
            bh = max(2.0, amp * (h - 14))
            if i <= play_i:
                col = QColor(M3["primary"]); col.setAlpha(230)
            else:
                col = QColor(M3["on_surface_variant"]); col.setAlpha(78)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x, mid - bh/2, self.BAR_W, bh), 1.5, 1.5)
        px = self.PAD + play_i * (self.BAR_W + self.GAP)
        if playing:
            g = QColor(M3["primary"]); g.setAlpha(55)
            p.setBrush(g); p.drawEllipse(QRectF(px - 8 - 3*self._pulse, mid - 8 - 3*self._pulse,
                                                16 + 6*self._pulse, 16 + 6*self._pulse))
        p.setBrush(QColor(M3["primary"]))
        p.drawEllipse(QRectF(px - 3.5, mid - 3.5, 7, 7))

    # ===== v17.3: Mode 1/2 — Bars / Mirror Bars (inspired by CAVA sdl_cava) =====
    def _paint_bars(self, p, w, h, mid, n, playing, math, mirror=False):
        p.setPen(Qt.NoPen)
        bw = self.bar_w; gap = self.gap
        total_w = n * (bw + gap) - gap
        start_x = max(self.PAD, (w - total_w) / 2)
        for i, lv in enumerate(self.bars):
            x = start_x + i * (bw + gap)
            amp = lv
            if playing:
                amp = min(1.0, amp * (1.0 + 0.3 * self._pulse))  # v17.4: REAL pulse, no fake sine
            bh = max(2.0, amp * (h - 6))
            if mirror:
                # Draw from center outward (both up and down)
                col = QColor(M3["primary"]); col.setAlpha(220)
                p.setBrush(col)
                radius = min(bw/2, 2.0) if self.rounded else 0
                p.drawRoundedRect(QRectF(x, mid - bh/2, bw, bh), radius, radius)
            else:
                # Draw from bottom up
                col = QColor(M3["primary"]); col.setAlpha(220)
                p.setBrush(col)
                radius = min(bw/2, 2.0) if self.rounded else 0
                p.drawRoundedRect(QRectF(x, h - bh - 2, bw, bh), radius, radius)

    # ===== v17.3: Mode 3 — Wave (inspired by Kurve waveRect + CAVA waveform) =====
    def _paint_wave(self, p, w, h, mid, n, playing, math):
        if n < 2: return
        step = (w - 2*self.PAD) / (n - 1)
        path = QPainterPath()
        path.moveTo(self.PAD, mid - self.bars[0] * (h/2 - 4))
        for i in range(1, n):
            x = self.PAD + i * step
            y = mid - self.bars[i] * (h/2 - 4)
            if playing:
                y -= 4 * self._pulse  # v17.4: REAL pulse, no fake sine
            # Smooth curve via quadratic to midpoint
            prev_x = self.PAD + (i-1) * step
            prev_y = mid - self.bars[i-1] * (h/2 - 4)
            mid_x = (prev_x + x) / 2
            mid_y = (prev_y + y) / 2
            path.quadTo(prev_x, prev_y, mid_x, mid_y)
        path.lineTo(w - self.PAD, mid - self.bars[-1] * (h/2 - 4))
        # Stroke the wave
        pen = QPen(QColor(M3["primary"])); pen.setWidthF(self.bar_w)
        pen.setCapStyle(Qt.RoundCap if self.rounded else Qt.SquareCap)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        # Fill below the wave (gradient)
        fill_path = QPainterPath(path)
        fill_path.lineTo(w - self.PAD, h)
        fill_path.lineTo(self.PAD, h)
        fill_path.closeSubpath()
        grad = QLinearGradient(0, 0, 0, h)
        c = QColor(M3["primary"]); c.setAlpha(80)
        grad.setColorAt(0, c); c2 = QColor(M3["primary"]); c2.setAlpha(10)
        grad.setColorAt(1, c2)
        p.setBrush(QBrush(grad)); p.setPen(Qt.NoPen)
        p.drawPath(fill_path)

    # ===== v17.3: Mode 4 — Radial Bars (inspired by CAVA orion_circle + Kurve barsCircle) =====
    def _paint_radial(self, p, w, h, mid, n, playing, math):
        cx, cy = w / 2, h / 2
        inner_r = min(w, h) * 0.15
        max_r = min(w, h) / 2 - 4
        angle_step = 2 * math.pi / max(n, 1)
        p.setPen(Qt.NoPen)
        for i, lv in enumerate(self.bars):
            amp = lv
            if playing:
                amp = min(1.0, amp * (1.0 + 0.4 * self._pulse))  # v17.4: REAL pulse, no fake sine
            bar_len = amp * (max_r - inner_r)
            angle = i * angle_step - math.pi / 2  # start at top
            x1 = cx + math.cos(angle) * inner_r
            y1 = cy + math.sin(angle) * inner_r
            x2 = cx + math.cos(angle) * (inner_r + bar_len)
            y2 = cy + math.sin(angle) * (inner_r + bar_len)
            pen = QPen(QColor(M3["primary"])); pen.setWidthF(self.bar_w)
            pen.setCapStyle(Qt.RoundCap if self.rounded else Qt.SquareCap)
            p.setPen(pen)
            p.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))
        # Draw inner ring
        p.setPen(QPen(QColor(M3["outline_variant"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPoint(int(cx), int(cy)), int(inner_r), int(inner_r))

    # ===== v17.3: Mode 5 — Blocks / LED VU-meter (inspired by Kurve blocksRect) =====
    def _paint_blocks(self, p, w, h, mid, n, playing, math):
        p.setPen(Qt.NoPen)
        bw = self.bar_w; gap = self.gap
        block_h = 4; block_gap = 1
        total_rows = int((h - 4) / (block_h + block_gap))
        total_w = n * (bw + gap) - gap
        start_x = max(self.PAD, (w - total_w) / 2)
        for i, lv in enumerate(self.bars):
            amp = lv
            if playing:
                amp = min(1.0, amp * (1.0 + 0.15 * self._pulse))
            active_rows = int(amp * total_rows)
            x = start_x + i * (bw + gap)
            for row in range(total_rows):
                y = h - (row + 1) * block_h - row * block_gap - 2
                if row < active_rows:
                    # Color gradient: green-ish at bottom → primary at top
                    ratio = row / max(1, total_rows - 1)
                    if ratio < 0.5:
                        col = QColor(M3["primary"]); col.setAlpha(220)
                    elif ratio < 0.8:
                        col = QColor(M3["tertiary"]); col.setAlpha(220)
                    else:
                        col = QColor(M3["error"]); col.setAlpha(220)
                else:
                    col = QColor(M3["surface_container_highest"]); col.setAlpha(60)
                p.setBrush(col)
                p.drawRoundedRect(QRectF(x, y, bw, block_h - 0.5), 1, 1)

# ===== v13.0 Fancy visual engine (FLB-inspired, native Qt) =====
def _rounded_pixmap(pm, radius):
    out = QPixmap(pm.size()); out.fill(Qt.transparent)
    p = QPainter(out); p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath(); path.addRoundedRect(QRectF(out.rect()), radius, radius)
    p.setClipPath(path); p.drawPixmap(0, 0, pm); p.end()
    return out

# ============================================================================
# v17.0 — EqualizerWidget: 10-band animated frequency visualizer
# Displays animated bars that respond to the current EQ gains + a live
# pseudo-spectrum animation when audio is playing. Pure QPainter motion graphics.
# ============================================================================

class EqualizerWidget(QWidget):
    """v17.0: Animated 10-band equalizer visualizer. Shows:
    - 10 vertical bars (one per frequency band: 31Hz to 16kHz)
    - Each bar's height = current gain (-12 to +12 dB) + a live animation
      overlay that pulses with the beat when audio is playing
    - Clickable: click on a bar to set its gain
    - Color: primary for positive gain, error for negative, outline for flat
    Pure QPainter rendering, 30fps while playing, 5fps when idle."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.win = None  # set by Win._build()
        self.gains = [EQ_DEFAULT_GAIN] * EQ_BANDS_COUNT
        self.anim_phase = 0.0
        self.idle_phase = 0.0
        self.hover_band = -1
        self.setMinimumHeight(180)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click a band to adjust gain (-12 to +12 dB)")
        # Animation timer
        self.timer = QTimer(self); self.timer.setInterval(33)  # ~30fps
        self.timer.timeout.connect(self._tick)
        self.idle_timer = QTimer(self); self.idle_timer.setInterval(200)  # 5fps idle
        self.idle_timer.timeout.connect(self._idle_tick)
        self.idle_timer.start()
    def set_gains(self, gains):
        """Set the 10-band gains (list of 10 ints, -12 to +12)."""
        self.gains = list(gains)[:EQ_BANDS_COUNT]
        while len(self.gains) < EQ_BANDS_COUNT:
            self.gains.append(EQ_DEFAULT_GAIN)
        self.update()
    def set_playing(self, playing):
        """Start/stop the live animation."""
        if playing:
            self.timer.start()
            self.idle_timer.stop()
        else:
            self.timer.stop()
            self.idle_timer.start()
    def _tick(self):
        import math
        self.anim_phase += 0.35
        self.update()
    def _idle_tick(self):
        self.idle_phase += 0.1
        self.update()
    def _band_at_x(self, x):
        """Return the band index (0-9) at the given x position, or -1."""
        w = self.width(); pad = 20
        bar_w = (w - 2 * pad) / EQ_BANDS_COUNT
        if x < pad or x > w - pad: return -1
        return min(EQ_BANDS_COUNT - 1, max(0, int((x - pad) / bar_w)))
    def _gain_at_y(self, y):
        """Return the gain (-12 to +12) corresponding to the y position."""
        h = self.height(); mid = h / 2
        # Top = +12, bottom = -12, middle = 0
        if y <= 10: return EQ_MAX_GAIN
        if y >= h - 10: return EQ_MIN_GAIN
        ratio = (mid - y) / (mid - 10)
        return max(EQ_MIN_GAIN, min(EQ_MAX_GAIN, int(round(ratio * EQ_MAX_GAIN))))
    def mouseMoveEvent(self, e):
        band = self._band_at_x(int(e.position().x()))
        if band != self.hover_band:
            self.hover_band = band
            self.update()
        super().mouseMoveEvent(e)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            band = self._band_at_x(int(e.position().x()))
            if band >= 0:
                gain = self._gain_at_y(int(e.position().y()))
                self.gains[band] = gain
                self.update()
                # Notify the parent (Win) to apply the gain
                if self.win and hasattr(self.win, "_on_eq_band_changed"):
                    self.win._on_eq_band_changed(band, gain)
    def mouseReleaseEvent(self, e):
        # Final notification on release (so dragging works)
        if e.button() == Qt.LeftButton and self.win and hasattr(self.win, "_on_eq_changed"):
            self.win._on_eq_changed(self.gains)
    def paintEvent(self, e):
        import math
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid = h / 2; pad = 20
        bar_w = (w - 2 * pad) / EQ_BANDS_COUNT
        bar_inner_w = bar_w * 0.6
        # Draw center line (0 dB reference)
        pen = QPen(QColor(M3["outline_variant"])); pen.setWidth(1)
        p.setPen(pen); p.drawLine(pad, int(mid), w - pad, int(mid))
        # Draw +6 dB and -6 dB reference lines
        for db_ref in (6, -6):
            y = mid - (db_ref / EQ_MAX_GAIN) * (mid - 10)
            pen.setColor(QColor(M3["outline_variant"])); pen.setStyle(Qt.DashLine)
            p.setPen(pen); p.drawLine(pad, int(y), w - pad, int(y))
        pen.setStyle(Qt.SolidLine); p.setPen(pen)
        # Draw each band bar
        playing = self.win.playing if (self.win and hasattr(self.win, "playing")) else False
        for i, gain in enumerate(self.gains):
            x = pad + i * bar_w + (bar_w - bar_inner_w) / 2
            # Base height from gain (-12 to +12 → 0 to full)
            gain_ratio = gain / EQ_MAX_GAIN  # -1 to +1
            base_h = abs(gain_ratio) * (mid - 10)
            # Animation overlay: pulse when playing
            if playing:
                pulse = 0.15 * math.sin(self.anim_phase + i * 0.7) + 0.1 * math.sin(self.anim_phase * 1.7 + i)
                anim_h = pulse * (mid - 10)
            else:
                anim_h = 0.05 * math.sin(self.idle_phase + i * 0.5) * (mid - 10)
            total_h = base_h + max(0, anim_h * 20)
            # Determine color: positive = primary, negative = error, flat = outline
            if gain > 0:
                col = QColor(M3["primary"])
                y_top = mid - total_h
                y_bot = mid
            elif gain < 0:
                col = QColor(M3["error"])
                y_top = mid
                y_bot = mid + total_h
            else:
                col = QColor(M3["outline"])
                y_top = mid - 2
                y_bot = mid + 2
            # Hover highlight
            if i == self.hover_band:
                col = col.lighter(130)
            col.setAlpha(220)
            p.setBrush(col); p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x, y_top, bar_inner_w, max(2, y_bot - y_top)), 3, 3)
            # Draw gain label below the bar
            p.setPen(QColor(M3["on_surface_variant"]))
            font = QFont(); font.setPointSize(8); p.setFont(font)
            label_y = h - 4
            p.drawText(QRectF(x - 5, label_y - 14, bar_inner_w + 10, 14),
                       Qt.AlignCenter, EQ_BAND_LABELS[i])
            # Draw gain value above the bar (only if non-zero or hovered)
            if gain != 0 or i == self.hover_band:
                val_text = f"{'+' if gain > 0 else ''}{gain}"
                p.setPen(QColor(M3["primary"]) if gain > 0 else
                         (QColor(M3["error"]) if gain < 0 else QColor(M3["outline"])))
                p.drawText(QRectF(x - 8, y_top - 16, bar_inner_w + 16, 14),
                           Qt.AlignCenter, val_text)
        p.end()

# ============================================================================
# v17.0 — AnimatedNowPlaying: pulsing album-art indicator + dancing bars
# ============================================================================

class AnimatedNowPlaying(QWidget):
    """v17.0: Small animated widget that sits in the player bar showing:
    - A pulsing dot when audio is playing
    - 4 dancing bars (mini equalizer) that bounce with the beat
    Pure motion graphics, ~20fps."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.win = None
        self.setFixedSize(48, 32)
        self.phase = 0.0
        self.timer = QTimer(self); self.timer.setInterval(50)  # ~20fps
        self.timer.timeout.connect(self._tick)
    def set_playing(self, playing):
        if playing: self.timer.start()
        else:
            self.timer.stop()
            self.update()  # one last paint to freeze
    def _tick(self):
        self.phase += 0.4
        self.update()
    def paintEvent(self, e):
        import math
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        playing = self.win.playing if (self.win and hasattr(self.win, "playing")) else False
        if not playing:
            # Show a paused icon (two vertical bars)
            p.setBrush(QColor(M3["on_surface_variant"]))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(w/2 - 7, 8, 4, 16), 1, 1)
            p.drawRoundedRect(QRectF(w/2 + 3, 8, 4, 16), 1, 1)
            p.end(); return
        # Pulsing dot on the left
        pulse = 0.5 + 0.5 * math.sin(self.phase * 0.8)
        dot_r = 4 + 2 * pulse
        dot_col = QColor(M3["primary"]); dot_col.setAlpha(int(180 + 60 * pulse))
        p.setBrush(dot_col); p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(6 - pulse, h/2 - dot_r, dot_r * 2, dot_r * 2))
        # 4 dancing bars on the right
        bar_x_start = 18; bar_w = 4; bar_gap = 3
        for i in range(4):
            x = bar_x_start + i * (bar_w + bar_gap)
            # Each bar has a different phase for a wave effect
            amp = 0.4 + 0.4 * math.sin(self.phase + i * 0.6)
            bar_h = 4 + amp * (h - 8)
            col = QColor(M3["primary"]); col.setAlpha(200)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x, (h - bar_h) / 2, bar_w, bar_h), 1.5, 1.5)
        p.end()

class Backdrop(QWidget):
    """Full-window blurred album-art background + dark scrim (FLB bg.vue).
    Blur = downscale to 24px + smooth upscale — one-time cost per track/resize,
    zero per-frame cost. Perfect for 4GB/Celeron machines."""
    def __init__(self):
        super().__init__()
        self._tiny = None      # 24px source (kept for re-scaling)
        self._scaled = None    # window-sized cached pixmap
    def set_art(self, img):
        if img is None or img.isNull():
            self._tiny = None; self._scaled = None
        else:
            self._tiny = QPixmap.fromImage(img.scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            self._rescale()
        self.update()
    def _rescale(self):
        if self._tiny and self.width() > 0:
            self._scaled = self._tiny.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    def resizeEvent(self, e):
        self._rescale(); super().resizeEvent(e)
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(M3["surface"]))
        if self._scaled:
            p.setOpacity(0.50); p.drawPixmap(0, 0, self._scaled); p.setOpacity(1.0)
            g = QLinearGradient(0, 0, 0, self.height())
            g.setColorAt(0.0, QColor(13, 14, 19, 150))
            g.setColorAt(1.0, QColor(13, 14, 19, 235))
            p.fillRect(self.rect(), QBrush(g))
        p.end()

class TrackDelegate(QStyledItemDelegate):
    """FLB track-card, natively: rounded row, 48px rounded album thumb,
    title + artist stacked, duration right, accent pill on the playing row.
    v15: generalized — `rows` / `current` providers let the same delegate
    paint the Library, the Queue and Playlist detail lists. Playing row gets
    a 3-bar dancing equalizer badge (motion graphic) while audio plays."""
    ROW_H = 64
    def __init__(self, win, rows=None, current=None):
        super().__init__(win); self.win = win
        self.rows = rows or (lambda: win.songs)
        self.current = current or (lambda: win.cur_idx)
        self._thumbs = {}  # path -> QPixmap (48px, rounded) | None
    def _thumb(self, song):
        path = song["path"]
        if path not in self._thumbs:
            pm = None
            if song.get("art"):
                img = QImage()
                if img.loadFromData(song["art"]) and not img.isNull():
                    pm = _rounded_pixmap(QPixmap.fromImage(
                        img.scaled(48, 48, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    ).copy(0, 0, 48, 48), 10)
            if len(self._thumbs) > 600: self._thumbs.clear()  # simple cap
            self._thumbs[path] = pm
        return self._thumbs[path]
    def invalidate(self, path=None):
        if path: self._thumbs.pop(path, None)
        else: self._thumbs.clear()
    def sizeHint(self, opt, idx):
        return QSize(0, self.ROW_H)
    def paint(self, p, opt, idx):
        i = idx.data(Qt.UserRole)
        rows = self.rows()
        if i is None or i >= len(rows):
            return super().paint(p, opt, idx)
        s = rows[i]
        playing = (i == self.current())
        r = opt.rect.adjusted(4, 2, -4, -2)
        p.save(); p.setRenderHint(QPainter.Antialiasing)
        # row background
        if playing:
            p.setPen(Qt.NoPen); p.setBrush(QColor(M3["secondary_container"]))
            p.drawRoundedRect(QRectF(r), 16, 16)
        elif opt.state & QStyle.State_MouseOver or opt.state & QStyle.State_Selected:
            p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 255, 18))
            p.drawRoundedRect(QRectF(r), 16, 16)
        # accent pill indicator (FLB ::before)
        if playing:
            p.setBrush(QColor(M3["primary"]))
            p.drawRoundedRect(QRectF(r.left() + 6, r.center().y() - 12, 4, 24), 2, 2)
        # album art thumb / placeholder
        tx = r.left() + 20
        ty = r.top() + (r.height() - 48) // 2
        pm = self._thumb(s)
        if pm:
            p.drawPixmap(tx, ty, pm)
        else:
            p.setPen(Qt.NoPen); p.setBrush(QColor(M3["surface_container_highest"]))
            p.drawRoundedRect(QRectF(tx, ty, 48, 48), 10, 10)
            p.setPen(QColor(M3["outline"]))
            f = p.font(); f.setPointSize(14); p.setFont(f)
            p.drawText(QRect(tx, ty, 48, 48), Qt.AlignCenter, "\u266B")
        # v15: dancing 3-bar EQ badge over the thumb while this row is playing
        if playing and self.win.playing:
            import math, time
            t = time.time() * 6.0
            p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 120))
            p.drawRoundedRect(QRectF(tx, ty, 48, 48), 10, 10)
            p.setBrush(QColor(M3["primary"]))
            for k in range(3):
                bh = 8 + 14 * abs(math.sin(t + k * 1.1))
                p.drawRoundedRect(QRectF(tx + 14 + k * 8, ty + 24 + 12 - bh, 4, bh), 2, 2)
        # duration (right)
        fm_r = r.right() - 16; dur_w = 0
        if s["duration"]:
            p.setPen(QColor(M3["on_secondary_container"] if playing else M3["on_surface_variant"]))
            f = p.font(); f.setPointSize(9); f.setBold(False); p.setFont(f)
            d = fmt_time(s["duration"])
            dur_w = QFontMetrics(f).horizontalAdvance(d) + 12
            p.drawText(QRect(fm_r - dur_w, r.top(), dur_w, r.height()), Qt.AlignVCenter | Qt.AlignRight, d)
        # title + artist
        text_x = tx + 48 + 14
        text_w = fm_r - dur_w - text_x - 8
        f = p.font(); f.setPointSize(11); f.setBold(True); p.setFont(f)
        p.setPen(QColor(M3["on_secondary_container"] if playing else M3["on_surface"]))
        title = QFontMetrics(f).elidedText(s["title"], Qt.ElideRight, text_w)
        p.drawText(QRect(text_x, r.top() + 10, text_w, 22), Qt.AlignVCenter | Qt.AlignLeft, title)
        f.setPointSize(9); f.setBold(False); p.setFont(f)
        p.setPen(QColor(M3["on_surface_variant"]))
        artist = QFontMetrics(f).elidedText(s["artist"], Qt.ElideRight, text_w)
        p.drawText(QRect(text_x, r.top() + 34, text_w, 18), Qt.AlignVCenter | Qt.AlignLeft, artist)
        p.restore()

# ===== Enums =====
class RepeatMode(Enum):
    OFF = 0; ALL = 1; ONE = 2
class SortMode(Enum):
    DATE = 0; TITLE = 1; ARTIST = 2; ALBUM = 3

# ===== Stylesheet (Material 3, v12.3) =====
# Every rule below maps a Qt widget to its Material 3 component + tokens.
# @token placeholders are substituted from the M3 dict by _m3ss().
def _m3ss(qss):
    for k in sorted(M3, key=len, reverse=True):  # longest first so @primary_container wins over @primary
        qss = qss.replace("@" + k, M3[k])
    return qss

# v15: kept as a template so the Settings hue slider can rebuild the QSS live
SS_TEMPLATE = """
/* Base — surface / on-surface, M3 type: body-large */
QMainWindow { background-color:@surface; }
/* v13: widgets are transparent so the blurred album-art backdrop shows through */
QWidget { background-color:transparent; color:@on_surface; font-family:"Roboto","Inter","Segoe UI",sans-serif; font-size:14px; }
QLabel { background:transparent; }
QToolTip { background-color:@inverse_surface; color:@inverse_on_surface; border:none; padding:4px 8px; border-radius:4px; font-size:12px; }
/* Navigation drawer -> surface-container-low */
QFrame#sidebar { background-color:rgba(27,27,33,0.60); border:none; border-right:1px solid rgba(255,255,255,0.04); }
QFrame#contentArea { background-color:transparent; }
/* Bottom app bar -> glassy surface-container */
QFrame#playerBar { background-color:rgba(31,31,37,0.72); border:none; border-top:1px solid rgba(255,255,255,0.05); }
QFrame#albumArt { background-color:@surface_container_highest; border-radius:12px; border:none; min-width:64px; min-height:64px; max-width:64px; max-height:64px; }
QFrame#queuePanel { background-color:@surface_container_low; border:none; }
/* Nav drawer item: 28px full-pill, active = secondary-container (M3 spec) */
QPushButton#navButton { text-align:left; padding:14px 24px; border:none; border-radius:24px; margin:2px 12px; min-height:20px; font-size:14px; font-weight:500; color:@on_surface_variant; background:transparent; }
QPushButton#navButton:hover { color:@on_surface; background-color:@state_hover_on_surface; }
QPushButton#navButton:pressed { background-color:@state_press_on_surface; }
QPushButton#navButton:checked { color:@on_secondary_container; background-color:@secondary_container; }
/* Type scale: title-small / headline-large / body-medium / title-medium / label */
QLabel#sidebarHeader { font-size:14px; font-weight:500; color:@on_surface_variant; padding:18px 28px 10px; }
QLabel#pageTitle { font-size:32px; font-weight:400; color:@on_surface; padding:24px 28px 4px; }
QLabel#pageSubtitle { font-size:14px; color:@on_surface_variant; padding:0 28px 16px; }
QLabel#titleLabel { font-size:16px; font-weight:500; color:@on_surface; }
QLabel#artistLabel { font-size:14px; color:@on_surface_variant; }
QLabel#timeLabel { font-size:11px; font-weight:500; color:@on_surface_variant; }
QLabel#queueHeader { font-size:22px; font-weight:400; color:@on_surface; padding:20px 20px 12px; }
QLabel#statusLabel { font-size:12px; font-weight:500; color:@on_surface_variant; padding:8px 28px; }
/* M3 search bar: full pill on surface-container-high */
QLineEdit#searchBar { background-color:rgba(41,42,47,0.75); border:1px solid rgba(255,255,255,0.06); border-radius:24px; padding:12px 20px 12px 44px; font-size:15px; color:@on_surface; margin:0 28px 16px; }
QLineEdit#searchBar:focus { border:1px solid @primary; }
/* Outlined dropdown (M3 outlined field) */
QComboBox#sortCombo { background-color:transparent; border:1px solid @outline; border-radius:4px; padding:8px 12px; font-size:14px; color:@on_surface; min-width:120px; }
QComboBox#sortCombo:hover { border-color:@on_surface; }
QComboBox QAbstractItemView { background-color:@surface_container; border:1px solid @outline_variant; border-radius:4px; selection-background-color:@secondary_container; selection-color:@on_secondary_container; color:@on_surface; padding:4px; }
/* Lists: state layers on hover, secondary-container when selected */
/* v13: song rows painted by TrackDelegate (thumb + 2-line + accent pill) */
QListWidget#songList { background-color:transparent; border:none; outline:none; padding:0 20px; }
QListWidget#songList::item { background:transparent; }
QListWidget#songList::item:hover { background:transparent; }
QListWidget#songList::item:selected { background:transparent; }
QListWidget#playlistList, QListWidget#queueList, QListWidget#sideQueueList { background-color:transparent; border:none; padding:0 20px; outline:none; }
QListWidget#playlistList::item, QListWidget#queueList::item, QListWidget#sideQueueList::item { padding:14px 16px; border-radius:12px; margin:1px 0; }
QListWidget#playlistList::item:hover, QListWidget#queueList::item:hover, QListWidget#sideQueueList::item:hover { background-color:@state_hover_on_surface; }
QListWidget#playlistList::item:selected, QListWidget#queueList::item:selected, QListWidget#sideQueueList::item:selected { background-color:@secondary_container; color:@on_secondary_container; }
/* Standard icon button (M3): circular, transparent, state layers */
QPushButton { background-color:transparent; border:none; color:@on_surface_variant; padding:8px; border-radius:20px; }
QPushButton:hover { background-color:@state_hover_on_surface; color:@on_surface; }
QPushButton:pressed { background-color:@state_press_on_surface; }
/* Play/pause = M3 FAB: 56dp, 16dp corner, primary-container */
QPushButton#playButton { background-color:@primary_container; color:@on_primary_container; border-radius:16px; min-width:56px; min-height:56px; max-width:56px; max-height:56px; border:none; }
QPushButton#playButton:hover { background-color:@primary_container_hover; }
QPushButton#playButton:pressed { background-color:@primary_container_press; }
/* Transport = standard icon buttons; checked (shuffle/repeat) = tonal */
QPushButton#controlButton { color:@on_surface_variant; padding:8px; min-width:40px; min-height:40px; border-radius:20px; background-color:transparent; border:none; }
QPushButton#controlButton:hover { color:@on_surface; background-color:@state_hover_on_surface; }
QPushButton#controlButton:pressed { background-color:@state_press_on_surface; }
QPushButton#controlButton:checked { color:@on_secondary_container; background-color:@secondary_container; }
/* Filled button (M3): full pill, primary / on-primary */
QPushButton#createBtn { background-color:@primary; color:@on_primary; border-radius:20px; padding:10px 24px; font-size:14px; font-weight:500; }
QPushButton#createBtn:hover { background-color:@primary_hover; }
QPushButton#createBtn:pressed { background-color:@primary_press; }
/* M3 slider: primary active track, surface-container-highest inactive */
QSlider::groove:horizontal { background:@surface_container_highest; height:4px; border-radius:2px; }
QSlider::handle:horizontal { background:@primary; width:16px; height:16px; margin:-6px 0; border-radius:8px; }
QSlider::handle:horizontal:hover { background:@primary; width:18px; height:18px; margin:-7px 0; border-radius:9px; }
QSlider::sub-page:horizontal { background:@primary; border-radius:2px; }
QSlider#volumeSlider::groove:horizontal { background:@surface_container_highest; height:4px; border-radius:2px; }
QSlider#volumeSlider::handle:horizontal { background:@primary; width:12px; height:12px; margin:-4px 0; border-radius:6px; }
QSlider#volumeSlider::sub-page:horizontal { background:@primary; border-radius:2px; }
/* Menus (context/tray): surface-container + state layers */
QMenu { background-color:@surface_container; color:@on_surface; border:1px solid @outline_variant; border-radius:4px; padding:8px 0; }
QMenu::item { padding:10px 16px; background:transparent; }
QMenu::item:selected { background-color:@state_hover_on_surface; }
QScrollBar:vertical { background:transparent; width:8px; margin:0; }
QScrollBar::handle:vertical { background:@outline_variant; border-radius:4px; min-height:40px; }
QScrollBar::handle:vertical:hover { background:@outline; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
/* ===== v15 additions ===== */
/* Filled tonal button (M3): secondary-container pill — queue/playlist actions */
QPushButton#tonalBtn { background-color:@secondary_container; color:@on_secondary_container; border-radius:20px; padding:10px 20px; font-size:14px; font-weight:500; }
QPushButton#tonalBtn:hover { background-color:@secondary_container_hover; }
QPushButton#tonalBtn:pressed { background-color:@secondary_container; }
QPushButton#tonalBtn:disabled { background-color:@surface_container_high; color:@outline; }
/* Danger (error-container) button — delete playlist / clear queue */
QPushButton#dangerBtn { background-color:transparent; color:@error; border:1px solid @outline_variant; border-radius:20px; padding:10px 20px; font-size:14px; font-weight:500; }
QPushButton#dangerBtn:hover { background-color:rgba(255,180,171,0.10); border-color:@error; }
/* Settings cards: surface-container-low, 16dp corners (M3 filled card) */
QFrame#settingsCard { background-color:rgba(27,27,33,0.66); border:1px solid rgba(255,255,255,0.05); border-radius:16px; }
QLabel#cardTitle { font-size:16px; font-weight:500; color:@on_surface; background:transparent; }
QLabel#cardDesc { font-size:12px; color:@on_surface_variant; background:transparent; }
/* Hue slider: rainbow groove, white ring handle */
QSlider#hueSlider::groove:horizontal { height:12px; border-radius:6px;
  background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #FF5252, stop:0.083 #FF9E51, stop:0.167 #FFE24F, stop:0.25 #A4E84E,
    stop:0.333 #4EE85C, stop:0.417 #4FE8A9, stop:0.5 #4FE5E8, stop:0.583 #4FA5E8,
    stop:0.667 #5157E8, stop:0.75 #9A4FE8, stop:0.833 #E84FE0, stop:0.917 #E84F98, stop:1 #FF5252); }
QSlider#hueSlider::handle:horizontal { background:#FFFFFF; border:3px solid @surface; width:18px; height:18px; margin:-6px 0; border-radius:12px; }
QSlider#hueSlider::sub-page:horizontal { background:transparent; }
/* Playlist detail header title */
QLabel#plDetailTitle { font-size:28px; font-weight:400; color:@on_surface; background:transparent; }
QLabel#plDetailSub { font-size:13px; color:@on_surface_variant; background:transparent; }
/* Song-picker dialog list */
QListWidget#pickerList { background-color:@surface_container_low; border:1px solid @outline_variant; border-radius:12px; outline:none; }
QListWidget#pickerList::item { padding:10px 14px; border-radius:8px; margin:1px 2px; }
QListWidget#pickerList::item:hover { background-color:@state_hover_on_surface; }
QListWidget#pickerList::item:selected { background-color:@secondary_container; color:@on_secondary_container; }
/* ===== v16.0 Browse additions ===== */
/* External Browse button (player bar): filled primary-container, square-rounded */
QPushButton#externalBrowseBtn { background-color:@primary_container; color:@on_primary_container; border-radius:14px; border:none; padding:0; }
QPushButton#externalBrowseBtn:hover { background-color:@primary_container_hover; }
QPushButton#externalBrowseBtn:pressed { background-color:@primary_container_press; }
/* Browse card: surface-container, 12dp corners, hover lifts to surface-container-high */
QFrame#browseCard { background-color:rgba(31,31,37,0.65); border:1px solid rgba(255,255,255,0.04); border-radius:14px; }
QFrame#browseCard:hover { background-color:rgba(41,42,47,0.85); border:1px solid @primary; }
/* Browse card text */
QLabel#browseTitle { font-size:13px; font-weight:500; color:@on_surface; background:transparent; padding:0; }
QLabel#browseArtist { font-size:12px; color:@on_surface_variant; background:transparent; padding:0; }
QLabel#browseMeta { font-size:11px; color:@outline; background:transparent; padding:0; }
QLabel#browseStatus { font-size:12px; color:@on_surface_variant; background:transparent; padding:0; }
/* v16.7: "Double-click to play" hint on Browse cards */
QLabel#browseHint { font-size:10px; color:@outline; background:transparent; padding:2px 0 0; font-style:italic; }
QLabel#browseSuggestLabel { font-size:12px; font-weight:500; color:@primary; background:transparent; padding:0; }
/* v17.0: Repeat info label (below song title in player bar) */
QLabel#repeatInfo { font-size:10px; color:@outline; background:transparent; padding:0; font-style:italic; }
QLabel#browseEmpty { font-size:16px; color:@outline; padding:60px 20px; }
/* v17.5: A-B Loop buttons */
QPushButton#abButton { background-color:@surface_container_high; color:@on_surface_variant; border:1px solid @outline_variant; border-radius:6px; font-size:10px; font-weight:600; padding:0; }
QPushButton#abButton:hover { background-color:@secondary_container; color:@on_secondary_container; border-color:@primary; }
QPushButton#abButton:checked { background-color:@primary; color:@on_primary; border-color:@primary; }
QPushButton#abClearBtn { background-color:transparent; color:@error; border:1px solid @outline_variant; border-radius:6px; font-size:9px; padding:0; }
QPushButton#abClearBtn:hover { background-color:rgba(255,180,171,0.10); border-color:@error; }
/* Browse card preview button: tonal (secondary-container) — v16.5: kept for compat */
QPushButton#browsePreviewBtn { background-color:@secondary_container; color:@on_secondary_container; border-radius:18px; padding:0; border:none; }
QPushButton#browsePreviewBtn:hover { background-color:@secondary_container_hover; }
/* Browse card download button: filled (primary) — the call-to-action */
QPushButton#browseDownloadBtn { background-color:@primary; color:@on_primary; border-radius:18px; padding:0; border:none; }
QPushButton#browseDownloadBtn:hover { background-color:@primary_hover; }
QPushButton#browseDownloadBtn:pressed { background-color:@primary_press; }
/* v16.5: wide Download button (replaces the icon-only one — single CTA per card) */
QPushButton#browseDownloadBtnWide { background-color:@primary; color:@on_primary; border-radius:18px; padding:0 14px; border:none; font-size:13px; font-weight:500; }
QPushButton#browseDownloadBtnWide:hover { background-color:@primary_hover; }
QPushButton#browseDownloadBtnWide:pressed { background-color:@primary_press; }
/* v16.5: infinite-scroll "loading more" footer label */
QLabel#browseLoadingMore { font-size:12px; color:@on_surface_variant; padding:14px 0; background:transparent; }
QLabel#browseEndOfResults { font-size:12px; color:@outline; padding:14px 0; background:transparent; }
/* Suggestion pill: outlined, hover fills with state layer */
QPushButton#suggestPill { background-color:transparent; color:@on_surface_variant; border:1px solid @outline_variant; border-radius:14px; padding:5px 14px; font-size:12px; }
QPushButton#suggestPill:hover { background-color:@state_hover_on_surface; color:@on_surface; border-color:@primary; }
/* Browse progress bar: thin, primary fill */
QProgressBar#browseProgress { background-color:@surface_container_high; border:none; border-radius:3px; }
QProgressBar#browseProgress::chunk { background-color:@primary; border-radius:3px; }
/* Browse scroll area: transparent so the backdrop shows through */
QScrollArea#browseScroll { background-color:transparent; border:none; }
QWidget#browseGrid { background-color:transparent; }
/* Browse search bar (overrides default searchBar — narrower margin for grid layout) */
QLineEdit#searchBar { background-color:rgba(41,42,47,0.85); border:1px solid rgba(255,255,255,0.08); border-radius:24px; padding:12px 20px; font-size:15px; color:@on_surface; margin:0; }
"""

def build_ss():
    """v15: rebuild the app stylesheet from the LIVE M3 palette."""
    return _m3ss(SS_TEMPLATE)

# ===== Utility =====
def get_metadata(fp):
    m = {"title":fp.stem,"artist":"Unknown","album":"","duration":0,"art":None,"path":str(fp),"date":fp.stat().st_mtime}
    if not HAS_MUTAGEN: return m
    try:
        a = MutagenFile(str(fp))
        if a is None: return m
        if hasattr(a,'info') and a.info.length: m["duration"]=int(a.info.length)
        if isinstance(a,MP3):
            t=a.tags or {}
            if "TIT2" in t: m["title"]=str(t["TIT2"])
            if "TPE1" in t: m["artist"]=str(t["TPE1"])
            if "TALB" in t: m["album"]=str(t["TALB"])
            for k in t:
                if k.startswith("APIC") and hasattr(t[k],'data'): m["art"]=t[k].data; break
        elif isinstance(a,MP4):
            t=a.tags or {}
            if "\xa9nam" in t: m["title"]=str(t["\xa9nam"][0])
            if "\xa9ART" in t: m["artist"]=str(t["\xa9ART"][0])
            if "\xa9alb" in t: m["album"]=str(t["\xa9alb"][0])
            if "covr" in t and t["covr"]: m["art"]=t["covr"][0] if isinstance(t["covr"][0],bytes) else None
        elif isinstance(a,FLAC):
            t=a.tags or {}
            if "title" in t: m["title"]=str(t["title"][0])
            if "artist" in t: m["artist"]=str(t["artist"][0])
            if "album" in t: m["album"]=str(t["album"][0])
            if a.pictures: m["art"]=a.pictures[0].data
    except: pass
    return m

def fmt_time(s):
    s=max(0,int(s)); h=s//3600; m=(s%3600)//60; sec=s%60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

def load_cfg():
    d={"vol":70,"repeat":"off","shuffle":False,"sort":"date","last":-1,"w":1100,"h":750,
       "theme_hue":DEFAULT_HUE,"show_viz":True}  # v15
    if CONFIG_FILE.exists():
        try: d.update(json.loads(CONFIG_FILE.read_text()))
        except: pass
    return d

def save_cfg(c):
    try: CONFIG_FILE.write_text(json.dumps(c,indent=2))
    except: pass

def load_pl():
    if PLAYLISTS_FILE.exists():
        try: return json.loads(PLAYLISTS_FILE.read_text())
        except: pass
    return {}

def save_pl(p):
    try: PLAYLISTS_FILE.write_text(json.dumps(p,indent=2))
    except: pass

# ===== v16.8: History persistence =====
# History stores the last 100 played songs with metadata:
#   - title, artist, path
#   - first_played (ISO datetime)
#   - last_played (ISO datetime)
#   - play_count (how many times this exact song was played)
#   - total_play_seconds (cumulative seconds this song has been the current track)
# Plus session stats:
#   - session_started (ISO datetime of current app launch)
#   - total_app_seconds (cumulative time across ALL sessions)
# FIFO eviction when > HISTORY_MAX_ENTRIES (100).

def load_history():
    """Load play history from HISTORY_FILE. Returns a dict:
    {
      "entries": [ {title, artist, path, first_played, last_played, play_count, total_play_seconds}, ... ],
      "play_counts": { "path": count, ... },  # aggregate across evicted entries
      "total_app_seconds": 12345.6,
    }
    Entries are ordered newest-first. Max HISTORY_MAX_ENTRIES entries."""
    default = {"entries": [], "play_counts": {}, "total_app_seconds": 0}
    if HISTORY_FILE.exists():
        try:
            d = json.loads(HISTORY_FILE.read_text())
            # Validate structure
            if "entries" not in d: d["entries"] = []
            if "play_counts" not in d: d["play_counts"] = {}
            if "total_app_seconds" not in d: d["total_app_seconds"] = 0
            return d
        except Exception: pass
    return default

def save_history(h):
    try: HISTORY_FILE.write_text(json.dumps(h, indent=2))
    except Exception as e: print(f"[Aurora][History] save failed: {e}", flush=True)

def record_play(title, artist, path, duration_sec=0):
    """v16.8: Record that a song was played. Called from play_idx/play_file.
    - If the song is already in history (matched by path), increment play_count
      and update last_played. Move it to the top (newest-first).
    - If new, insert at top with play_count=1.
    - If history exceeds HISTORY_MAX_ENTRIES, evict the oldest entry (but
      preserve its play_count in play_counts so aggregate stats survive).
    Returns the updated history dict."""
    h = load_history()
    now = datetime.now().isoformat()
    entries = h.get("entries", [])
    play_counts = h.get("play_counts", {})
    # Try to find existing entry by path (or by title+artist if path is empty)
    existing_idx = -1
    for i, e in enumerate(entries):
        if path and e.get("path") == path:
            existing_idx = i; break
        if not path and e.get("title") == title and e.get("artist") == artist:
            existing_idx = i; break
    if existing_idx >= 0:
        # Update existing
        e = entries.pop(existing_idx)
        e["play_count"] = e.get("play_count", 0) + 1
        e["last_played"] = now
        if not e.get("first_played"): e["first_played"] = now
        e["title"] = title or e.get("title", "")
        e["artist"] = artist or e.get("artist", "")
        if path: e["path"] = path
    else:
        # New entry
        e = {
            "title": title or "",
            "artist": artist or "",
            "path": path or "",
            "first_played": now,
            "last_played": now,
            "play_count": 1,
            "total_play_seconds": 0,
        }
    # Insert at top (newest-first)
    entries.insert(0, e)
    # FIFO eviction: if > MAX, evict oldest (last in list)
    while len(entries) > HISTORY_MAX_ENTRIES:
        evicted = entries.pop()
        # Preserve aggregate play_count for evicted entries
        ep = evicted.get("path") or f"{evicted.get('title','')}|{evicted.get('artist','')}"
        play_counts[ep] = play_counts.get(ep, 0) + evicted.get("play_count", 0)
    h["entries"] = entries
    h["play_counts"] = play_counts
    save_history(h)
    return h

def load_session():
    """v16.8: Load session tracking data. Returns dict with:
    - session_started: ISO datetime of current app launch (set fresh each launch)
    - total_app_seconds: cumulative time across ALL sessions (persisted)"""
    default = {"session_started": datetime.now().isoformat(), "total_app_seconds": 0}
    if SESSION_FILE.exists():
        try:
            d = json.loads(SESSION_FILE.read_text())
            # Always reset session_started on launch
            d["session_started"] = datetime.now().isoformat()
            return d
        except Exception: pass
    return default

def save_session(s):
    try: SESSION_FILE.write_text(json.dumps(s, indent=2))
    except Exception as e: print(f"[Aurora][Session] save failed: {e}", flush=True)

def fmt_duration(seconds):
    """v16.8: Format seconds into human-readable duration.
    90 → '1m 30s', 3725 → '1h 2m 5s', 86400 → '1d 0h 0m'"""
    try: seconds = int(seconds)
    except: seconds = 0
    if seconds < 60: return f"{seconds}s"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"
    if seconds < 86400:
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m}m {s}s"
    d, rem = divmod(seconds, 86400)
    h, rem2 = divmod(rem, 3600)
    m, _ = divmod(rem2, 60)
    return f"{d}d {h}h {m}m"

# ===== v17.0: Equalizer persistence =====

def load_equalizer():
    """v17.0: Load 10-band EQ gains from EQUALIZER_FILE.
    Returns: { "enabled": bool, "gains": [10 ints], "preset": str }"""
    default = {
        "enabled": False,
        "gains": [EQ_DEFAULT_GAIN] * EQ_BANDS_COUNT,
        "preset": "Flat",
    }
    if EQUALIZER_FILE.exists():
        try:
            d = json.loads(EQUALIZER_FILE.read_text())
            if "gains" not in d: d["gains"] = list(default["gains"])
            if "enabled" not in d: d["enabled"] = False
            if "preset" not in d: d["preset"] = "Flat"
            # Ensure 10 bands
            while len(d["gains"]) < EQ_BANDS_COUNT: d["gains"].append(0)
            d["gains"] = d["gains"][:EQ_BANDS_COUNT]
            return d
        except Exception: pass
    return default

def save_equalizer(eq):
    """v17.0: Save EQ config to EQUALIZER_FILE."""
    try: EQUALIZER_FILE.write_text(json.dumps(eq, indent=2))
    except Exception as e: print(f"[Aurora][EQ] save failed: {e}", flush=True)

# ===== v17.0: Repeat/skip stats persistence =====
# Tracks per-song repeat count + global skip-forward/skip-backward counts.
# Stored separately from history so it survives history clearing.

def load_repeat_stats():
    """v17.0: Load repeat/skip stats. Returns:
    {
      "song_repeats": { "path": count, ... },  # how many times each song was repeated
      "skip_forward_count": int,  # total times user pressed next/skip-forward
      "skip_backward_count": int,  # total times user pressed prev/skip-backward
      "last_played_at": { "path": ISO_datetime, ... },  # last play time per song
    }"""
    default = {
        "song_repeats": {},
        "skip_forward_count": 0,
        "skip_backward_count": 0,
        "last_played_at": {},
    }
    if REPEAT_STATS_FILE.exists():
        try:
            d = json.loads(REPEAT_STATS_FILE.read_text())
            for k in default:
                if k not in d: d[k] = default[k]
            return d
        except Exception: pass
    return default

def save_repeat_stats(rs):
    """v17.0: Save repeat/skip stats to REPEAT_STATS_FILE."""
    try: REPEAT_STATS_FILE.write_text(json.dumps(rs, indent=2))
    except Exception as e: print(f"[Aurora][RepeatStats] save failed: {e}", flush=True)

def record_repeat(path, title=""):
    """v17.0: Record that a song was repeated (played again). Increments the
    song_repeats counter for this path."""
    rs = load_repeat_stats()
    key = path or title
    if not key: return
    rs["song_repeats"][key] = rs["song_repeats"].get(key, 0) + 1
    rs["last_played_at"][key] = datetime.now().isoformat()
    save_repeat_stats(rs)
    return rs["song_repeats"][key]

def record_skip(direction):
    """v17.0: Record a skip event. direction = 'forward' or 'backward'."""
    rs = load_repeat_stats()
    if direction == "forward":
        rs["skip_forward_count"] = rs.get("skip_forward_count", 0) + 1
    elif direction == "backward":
        rs["skip_backward_count"] = rs.get("skip_backward_count", 0) + 1
    save_repeat_stats(rs)

def get_song_repeat_count(path, title=""):
    """v17.0: Get how many times a song was repeated."""
    rs = load_repeat_stats()
    key = path or title
    return rs["song_repeats"].get(key, 0)

# ============================================================================
# v16.0 — BROWSE FEATURE
# Reverse-engineered from JustAnotherMusicClient's DataSource pattern +
# youtube-music-cli's download.service.ts flow, but using iTunes Search API
# (free, no API key, generous rate limit, returns 30-sec previewUrl +
# artworkUrl100 + full metadata) instead of YouTube Music internals.
#
# Classes:
#   - BrowseTrack       : dataclass for a single search result
#   - BrowseFetcher     : QThread — iTunes search (debounced caller-side)
#   - SuggestFetcher    : QThread — iTunes suggest (debounced caller-side)
#   - ThumbnailLoader   : QObject — async QNetworkAccessManager thumb loader
#   - Downloader        : QThread — downloads previewUrl to ~/Downloads/
#   - BrowseResultGrid  : QFrame  — one card in the results grid (thumb +
#                          title/artist + Preview + Download buttons)
# ============================================================================

from urllib.parse import quote_plus, urlencode
import urllib.request as _urlreq
import urllib.error as _urlerr

class BrowseTrack:
    """A single browse search result (iTunes track row)."""
    __slots__ = ("track_id", "title", "artist", "album", "genre", "duration_ms",
                 "artwork_url", "preview_url", "track_url", "release_date",
                 "country", "is_streamable")
    def __init__(self, d):
        self.track_id      = str(d.get("trackId", ""))
        self.title         = (d.get("trackName") or "").strip()
        self.artist        = (d.get("artistName") or "").strip()
        self.album         = (d.get("collectionName") or "").strip()
        self.genre         = (d.get("primaryGenreName") or "").strip()
        self.duration_ms   = int(d.get("trackTimeMillis") or 0)
        self.artwork_url   = (d.get("artworkUrl100") or "").strip()
        self.preview_url   = (d.get("previewUrl") or "").strip()
        self.track_url     = (d.get("trackViewUrl") or "").strip()
        self.release_date  = (d.get("releaseDate") or "")[:10]
        self.country       = (d.get("country") or "US")
        self.is_streamable = bool(d.get("isStreamable", False))
    def artwork(self, size=300):
        """Hi-res artwork: swap the 100x100bb token in the URL for any size."""
        if not self.artwork_url: return ""
        # iTunes serves /100x100bb.jpg — replace with /{size}x{size}bb.jpg
        return self.artwork_url.replace("100x100bb", f"{size}x{size}bb")
    def safe_filename(self, ext="mp3"):
        """Sanitized filename for download: 'Artist - Title.mp3'
        v16.5: default ext is now 'mp3' (yt-dlp + ffmpeg full-track download).
        Was 'm4a' in v16.0 (iTunes 30-sec preview)."""
        raw = f"{self.artist} - {self.title}".strip(" -")
        clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', raw).strip().strip('.')
        clean = re.sub(r'\s+', ' ', clean)
        if not clean: clean = f"aurora_track_{self.track_id}"
        return f"{clean}.{ext}"
    def search_query(self):
        """v16.5: YouTube search query for yt-dlp — 'artist title' (best match)."""
        return f"{self.artist} {self.title}".strip()
    def to_dict(self):
        return {
            "track_id": self.track_id, "title": self.title, "artist": self.artist,
            "album": self.album, "genre": self.genre, "duration_ms": self.duration_ms,
            "artwork_url": self.artwork_url, "preview_url": self.preview_url,
            "track_url": self.track_url, "release_date": self.release_date,
        }
    @staticmethod
    def from_dict(d):
        bt = BrowseTrack.__new__(BrowseTrack)
        for k in BrowseTrack.__slots__:
            setattr(bt, k, d.get(k, "") if k != "duration_ms" else int(d.get(k, 0) or 0))
        return bt

def _itunes_get(url, params, timeout=12):
    """Synchronous urllib GET to iTunes API. Returns parsed JSON dict or {}."""
    try:
        full = url + "?" + urlencode(params)
        req = _urlreq.Request(full, headers={"User-Agent": "Aurora-Music/16.0 (+https://aurora.local)"})
        with _urlreq.urlopen(req, timeout=timeout) as r:
            data = r.read().decode("utf-8", "replace")
        return json.loads(data) if data else {}
    except (_urlerr.URLError, _urlerr.HTTPError, json.JSONDecodeError, TimeoutError, OSError) as e:
        print(f"[Aurora][Browse] iTunes GET failed: {e}", flush=True)
        return {}

class BrowseFetcher(QThread):
    """Background iTunes search. Emit results(list[BrowseTrack], is_first_page,
    has_more) on done. Caller-side debouncing (BROWSE_DEBOUNCE_MS) avoids
    firing one request per keystroke — see Win._on_browse_text_changed.

    v16.5: iTunes' `offset` parameter is documented but UNRELIABLE (it often
    returns the same results regardless of offset). So we take a different
    approach to infinite scroll:
      - The FIRST call fetches ALL results up to BROWSE_MAX_TOTAL_RESULTS (200)
        in one shot (iTunes allows limit up to 200).
      - We then render them in pages of BROWSE_RESULT_LIMIT (50) — the caller
        calls _fire_browse_load_more() to reveal the next 50 from the buffer.
      - No second network call is needed; "load more" just renders more cards
        from the already-fetched buffer.
      - has_more reflects whether there are un-rendered cards in the buffer.

    This gives the same infinite-scroll feel (cards appear progressively as
    the user scrolls) without relying on iTunes' broken offset parameter.
    The `offset` parameter is still accepted on the search() call for
    backward-compat with the CLI `--browse-itunes <q> <country> <offset>`
    headless command, but it's a no-op for the GUI infinite scroll."""
    done = Signal(list, bool, bool)  # (tracks, is_first_page, has_more)
    error = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent); self._query = ""; self._country = "US"; self._offset = 0
    def search(self, query, country="US", offset=0):
        if self.isRunning():
            # v16: cancel the in-flight request by detaching — the QThread will
            # finish its urllib call (we can't kill it) but its `done` signal
            # will be ignored because a newer request will have superseded it
            # via the _browse_request_id race guard in Win.
            return
        self._query = (query or "").strip()
        self._country = country or "US"
        # v16.5: offset is kept for CLI compat but ignored by the GUI — we
        # always fetch the full result set on the first call.
        self._offset = max(0, int(offset))
        if not self._query: self.done.emit([], True, False); return
        self.start()
    def run(self):
        if not self._query: self.done.emit([], True, False); return
        # v16.5: fetch ALL results up to BROWSE_MAX_TOTAL_RESULTS (200) in one
        # call. iTunes' `offset` parameter is unreliable, so we don't paginate
        # at the network layer — we paginate at the render layer instead.
        limit = BROWSE_MAX_TOTAL_RESULTS
        params = {
            "term": self._query, "media": ITUNES_MEDIA, "entity": ITUNES_ENTITY,
            "limit": limit, "country": self._country,
        }
        data = _itunes_get(ITUNES_SEARCH_URL, params)
        results = data.get("results", []) if data else []
        tracks = [BrowseTrack(r) for r in results if r.get("trackName")]
        # De-dup by (title+artist) — iTunes sometimes returns the same track from
        # multiple storefronts.
        seen = set(); out = []
        for t in tracks:
            key = (t.title.lower(), t.artist.lower())
            if key in seen: continue
            seen.add(key); out.append(t)
        is_first = True  # v16.5: always first page (we fetched everything)
        # has_more is computed by the caller based on the buffer — we just
        # return all tracks and let Win._fire_browse_load_more paginate them.
        self.done.emit(out, is_first, False)

class SuggestFetcher(QThread):
    """Background iTunes suggest. We piggyback on the search endpoint with a
    small limit (BROWSE_SUGGEST_LIMIT) and take unique title+artist strings.
    200-250ms debounce on the caller side keeps it cheap."""
    done = Signal(list)
    def __init__(self, parent=None):
        super().__init__(parent); self._query = ""; self._country = "US"
    def suggest(self, query, country="US"):
        if self.isRunning(): return
        self._query = (query or "").strip(); self._country = country or "US"
        if len(self._query) < 2: self.done.emit([]); return
        self.start()
    def run(self):
        if len(self._query) < 2: self.done.emit([]); return
        params = {
            "term": self._query, "media": ITUNES_MEDIA, "entity": ITUNES_ENTITY,
            "limit": BROWSE_SUGGEST_LIMIT * 2, "country": self._country,
        }
        data = _itunes_get(ITUNES_SEARCH_URL, params)
        results = data.get("results", []) if data else []
        seen = set(); suggestions = []
        for r in results:
            title = (r.get("trackName") or "").strip()
            artist = (r.get("artistName") or "").strip()
            if title and title not in seen:
                seen.add(title); suggestions.append(title)
            if artist and artist not in seen:
                seen.add(artist); suggestions.append(artist)
            if len(suggestions) >= BROWSE_SUGGEST_LIMIT: break
        self.done.emit(suggestions)

class ThumbnailLoader(QObject):
    """Async thumbnail loader using QNetworkAccessManager.
    Caches QPixmap by URL (LRU). Calls callback(QPixmap) on done — always on
    the Qt main thread (QNetworkAccessManager signal)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._cache = {}  # url -> QPixmap (LRU; capped at 200)
        self._pending = {}  # url -> list of callbacks
        self._replies = {}  # reply -> url
    def load(self, url, callback, size=BROWSE_THUMB_SIZE):
        """Fetch `url` (or cached pixmap) and call `callback(QPixmap)`."""
        if not url:
            callback(_svg_pixmap(IC_MUSIC, M3["outline_variant"], size)); return
        if url in self._cache:
            callback(self._cache[url]); return
        # Pending request — append callback; will be invoked when reply arrives
        if url in self._pending:
            self._pending[url].append((callback, size)); return
        self._pending[url] = [(callback, size)]
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute,
                         QNetworkRequest.NoLessSafeRedirectPolicy)
        req.setRawHeader(b"User-Agent", b"Aurora-Music/16.0")
        reply = self._nam.get(req)
        self._replies[reply] = url
        reply.finished.connect(lambda r=reply: self._on_finished(r))
    def _on_finished(self, reply):
        url = self._replies.pop(reply, None)
        cbs = self._pending.pop(url, []) if url else []
        if reply.error() != QNetworkReply.NoError:
            pm = _svg_pixmap(IC_MUSIC, M3["outline_variant"], BROWSE_THUMB_SIZE)
        else:
            data = bytes(reply.readAll())
            pm = QPixmap()
            if not pm.loadFromData(data):
                pm = _svg_pixmap(IC_MUSIC, M3["outline_variant"], BROWSE_THUMB_SIZE)
        reply.deleteLater()
        # Cache (LRU eviction)
        if url:
            if len(self._cache) >= 200:
                self._cache.pop(next(iter(self._cache)), None)
            self._cache[url] = pm
        for cb, sz in cbs:
            if pm.size() != QSize(sz, sz) and not pm.isNull():
                cb(pm.scaled(sz, sz, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            else:
                cb(pm)
    def clear_cache(self):
        self._cache.clear()

def _svg_pixmap(path_data, fill, size=96):
    """Render a Material Symbols path as a QPixmap (used for thumbnail fallbacks)."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
           f'fill="{fill}" width="{size}" height="{size}"><path d="{path_data}"/></svg>')
    r = QSvgRenderer(svg.encode())
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); r.render(p); p.end()
    return pm

class Downloader(QThread):
    """v16.6: Background FULL-TRACK download with multi-strategy YouTube
    bot-protection bypass. Reverse-engineered from:
      - JustAnotherMusicClient's 5-client-type matrix (lib.rs lines 1518-1648)
      - JustAnotherMusicClient's SAPISIDHASH computation (tauriFetch.ts lines 92-128)
      - youtube-music-cli's Invidious 3-instance fallback (api.ts lines 1041-1101)
      - youtube-music-cli's yt-dlp + mpv fallback chain (download.service.ts)

    Strategy order (tried in sequence until one succeeds):
      1. yt-dlp --cookies-from-browser <browser>  (auto-detect installed browser)
      2. yt-dlp --cookies <cookies.txt>           (Netscape format, user-provided)
      3. yt-dlp --extractor-args "youtube:player_client=ios,android,tv,web,web_safari"
                                                   (client-type rotation)
      4. Invidious API fallback                    (3 instances, audio URL → ffmpeg)
      5. Innertube /youtubei/v1/player direct     (SAPISIDHASH + 5 client types)
      6. Plain yt-dlp                              (last resort — works for non-protected videos)

    For each strategy: search YouTube → pick best match → download audio →
    ffmpeg convert to MP3 → mutagen tag with iTunes metadata + cover art.
    If a strategy hits "Sign in to confirm you're not a bot", log it and try
    the next strategy. The first successful strategy wins.

    Emits progress(track_id, pct), done(track_id, path, ok, error), and
    strategy_used(track_id, strategy_name) when a strategy succeeds.
    """
    progress = Signal(str, int)
    done = Signal(str, str, bool, str)
    strategy_used = Signal(str, str)  # (track_id, strategy_name) — for UI display
    # Phase boundaries (percentages)
    P_SEARCH_DONE  = 5
    P_DOWNLOAD_MAX = 85
    P_CONVERT_DONE = 95
    P_TAG_DONE     = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._track = None
        self._cancel = False
        # v16.6: auth config (read fresh from cfg on each download() call)
        self._auth_strategy = "auto"     # "auto" | "browser" | "cookies_file" | "innertube" | "none"
        self._browser_choice = "firefox" # which browser to pull cookies from
        self._cookies_file = ""          # path to user-provided cookies.txt
        self._cookies_str = ""           # raw cookie header for Innertube (SAPISID etc)
    def download(self, track):
        """track: BrowseTrack. Start the QThread."""
        if self.isRunning():
            return False
        self._track = track
        self._cancel = False
        # v16.6: load auth config from cfg (so settings changes take effect immediately)
        try:
            cfg = load_cfg()
            self._auth_strategy  = cfg.get("yt_auth_strategy",  "auto")
            self._browser_choice = cfg.get("yt_browser_choice", "firefox")
            self._cookies_file   = cfg.get("yt_cookies_file",   "")
            self._cookies_str    = cfg.get("yt_cookies_str",    "")
        except Exception:
            pass  # fall back to defaults
        if not track or not track.title:
            self.done.emit(track.track_id if track else "", "", False, "No track title")
            return False
        self.start()
        return True
    def cancel(self):
        """v16.5: best-effort cancel — sets a flag the run() loop checks."""
        self._cancel = True
    def _find_ytdlp(self):
        """Locate yt-dlp executable. Tries PATH, then ~/.local/bin/yt-dlp."""
        from shutil import which
        p = which("yt-dlp")
        if p: return p
        p2 = Path.home() / ".local" / "bin" / "yt-dlp"
        if p2.exists() and os.access(p2, os.X_OK): return str(p2)
        return None
    def _find_ffmpeg(self):
        from shutil import which
        return which("ffmpeg") or which("ffmpeg.exe")
    def _subprocess_env(self):
        """v16.5: build an environment for yt-dlp/ffmpeg subprocesses.
        Includes PYTHONPATH so yt-dlp can find its own yt_dlp package when
        installed via pip --user."""
        env = os.environ.copy()
        try:
            import yt_dlp  # type: ignore
            yt_dlp_dir = os.path.dirname(os.path.dirname(yt_dlp.__file__))
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = yt_dlp_dir + (os.pathsep + existing if existing else "")
        except ImportError:
            for candidate in [
                str(Path.home() / ".local" / "lib" / "python3.13" / "site-packages"),
                str(Path.home() / ".local" / "lib" / "python3.12" / "site-packages"),
                str(Path.home() / ".local" / "lib" / "python3.11" / "site-packages"),
            ]:
                if Path(candidate, "yt_dlp").exists():
                    existing = env.get("PYTHONPATH", "")
                    env["PYTHONPATH"] = candidate + (os.pathsep + existing if existing else "")
                    break
        local_bin = str(Path.home() / ".local" / "bin")
        env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")
        return env
    def _emit(self, tid, pct):
        if not self._cancel:
            self.progress.emit(tid, pct)
    def _is_bot_blocked(self, stderr_text):
        """v16.6: detect YouTube's 'Sign in to confirm you're not a bot' error."""
        if not stderr_text: return False
        markers = ("Sign in to confirm", "not a bot", "bot detection",
                   "cookies-from-browser", "Unable to extract")
        low = stderr_text.lower()
        return any(m.lower() in low for m in markers)
    def _search_youtube(self, ytdlp, search_query):
        """v16.6: search YouTube via yt-dlp ytsearch3. Returns video_id or None.
        Anonymous search usually works (no auth needed) even when downloads don't."""
        cmd = [ytdlp, "--flat-playlist", "--print", "%(id)s|%(title)s|%(duration)s",
               "--no-warnings", "--no-playlist", f"ytsearch3:{search_query}"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=30, check=False, env=self._subprocess_env())
        except subprocess.TimeoutExpired:
            return None, "yt-dlp search timed out (30s)"
        if proc.returncode != 0:
            return None, (proc.stderr or "").strip().split("\n")[0][:200]
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        if not lines:
            return None, "YouTube search returned no results"
        parts = lines[0].split("|", 2)
        return parts[0].strip(), None

    # ====================================================================
    # v16.6 STRATEGY 1: yt-dlp --cookies-from-browser
    # ====================================================================
    def _try_cookies_from_browser(self, ytdlp, watch_url, out_tmpl, tid):
        """Strategy 1: use yt-dlp --cookies-from-browser <browser>.
        yt-dlp will read the browser's cookie store and use it for auth.
        Works if the user is signed into YouTube in that browser."""
        if self._auth_strategy not in ("auto", "browser"):
            return None, "skipped (auth_strategy != browser/auto)"
        browser = self._browser_choice or "firefox"
        print(f"[Aurora][Browse] Strategy 1: cookies-from-browser {browser!r}", flush=True)
        cmd = [ytdlp, "--no-warnings", "--no-playlist", "--no-progress", "--newline",
               "--cookies-from-browser", browser,
               "--extract-audio", "--audio-format", "mp3", "--audio-quality", "2",
               "-o", out_tmpl, "--print", "after_move:filepath", watch_url]
        return self._run_ytdlp_download(cmd, tid, "cookies-from-browser")

    # ====================================================================
    # v16.6 STRATEGY 2: yt-dlp --cookies <cookies.txt>
    # ====================================================================
    def _try_cookies_file(self, ytdlp, watch_url, out_tmpl, tid):
        """Strategy 2: use yt-dlp --cookies <file>.
        The user provides a Netscape-format cookies.txt (exported from a
        browser extension like 'Get cookies.txt LOCALLY')."""
        if self._auth_strategy not in ("auto", "cookies_file"):
            return None, "skipped (auth_strategy != cookies_file/auto)"
        cookies_path = self._cookies_file or ""
        if not cookies_path or not Path(cookies_path).exists():
            return None, "no cookies.txt file configured"
        print(f"[Aurora][Browse] Strategy 2: cookies file {cookies_path!r}", flush=True)
        cmd = [ytdlp, "--no-warnings", "--no-playlist", "--no-progress", "--newline",
               "--cookies", cookies_path,
               "--extract-audio", "--audio-format", "mp3", "--audio-quality", "2",
               "-o", out_tmpl, "--print", "after_move:filepath", watch_url]
        return self._run_ytdlp_download(cmd, tid, "cookies-file")

    # ====================================================================
    # v16.6 STRATEGY 3: yt-dlp --extractor-args client-type rotation
    # ====================================================================
    def _try_client_rotation(self, ytdlp, watch_url, out_tmpl, tid):
        """Strategy 3: yt-dlp with multiple player_clients extractor-args.
        Tries iOS → Android → TV → Web → Web Safari in order. Mobile clients
        are less likely to trigger bot detection (copy JustAnotherMusicClient
        lib.rs lines 1518-1532)."""
        if self._auth_strategy not in ("auto", "none"):
            return None, "skipped (auth_strategy != none/auto)"
        print(f"[Aurora][Browse] Strategy 3: client rotation {YTDLP_PLAYER_CLIENTS!r}", flush=True)
        cmd = [ytdlp, "--no-warnings", "--no-playlist", "--no-progress", "--newline",
               "--extract-audio", "--audio-format", "mp3", "--audio-quality", "2",
               "--extractor-args", f"youtube:player_client={YTDLP_PLAYER_CLIENTS}",
               "-o", out_tmpl, "--print", "after_move:filepath", watch_url]
        return self._run_ytdlp_download(cmd, tid, "client-rotation")

    # ====================================================================
    # v16.6 STRATEGY 4: Invidious API fallback (3 instances)
    # ====================================================================
    def _try_invidious(self, ffmpeg, video_id, dest, tid):
        """Strategy 4: query Invidious API for the audio URL, then ffmpeg it.
        Reverse-engineered from youtube-music-cli/api.ts lines 1041-1101.
        Tries 3 instances in order: vid.puffyan.us, invidious.perennialte.ch, yewtu.be."""
        if self._auth_strategy not in ("auto", "none"):
            return None, "skipped (auth_strategy != none/auto)"
        print(f"[Aurora][Browse] Strategy 4: Invidious fallback", flush=True)
        self._emit(tid, 10)
        audio_url = None
        for instance in INVIDIOUS_INSTANCES:
            try:
                api_url = f"{instance}/api/v1/videos/{video_id}"
                req = _urlreq.Request(api_url, headers={"User-Agent": "Aurora-Music/16.6"})
                with _urlreq.urlopen(req, timeout=15) as r:
                    data = json.loads(r.read().decode("utf-8", "replace"))
                # Collect all audio formats (adaptiveFormats + formatStreams)
                audio_formats = []
                for f in (data.get("adaptiveFormats") or []):
                    if f.get("type", "").lower().startswith("audio") and f.get("url"):
                        audio_formats.append(f)
                for f in (data.get("formatStreams") or []):
                    if "audio" in f.get("type", "").lower() and f.get("url"):
                        audio_formats.append(f)
                if audio_formats:
                    # Pick the highest-bitrate audio
                    audio_formats.sort(key=lambda f: int(f.get("bitrate", 0) or 0), reverse=True)
                    audio_url = audio_formats[0]["url"]
                    print(f"[Aurora][Browse] Invidious {instance} returned audio URL", flush=True)
                    break
            except Exception as e:
                print(f"[Aurora][Browse] Invidious {instance} failed: {e}", flush=True)
                continue
        if not audio_url:
            return None, "all 3 Invidious instances failed"
        # Download the audio URL via ffmpeg → MP3
        tmp_src = str(MUSIC_FOLDER / ".aurora-tmp" / f"invidious_{tid}.src")
        Path(tmp_src).parent.mkdir(parents=True, exist_ok=True)
        self._emit(tid, 50)
        cmd_ff = [ffmpeg, "-y", "-i", audio_url, "-vn", "-acodec", "libmp3lame",
                  "-q:a", "2", tmp_src]
        try:
            proc = subprocess.run(cmd_ff, capture_output=True, text=True,
                                  timeout=180, check=False)
        except subprocess.TimeoutExpired:
            return None, "ffmpeg (Invidious) timed out"
        if proc.returncode != 0 or not Path(tmp_src).exists():
            return None, f"ffmpeg (Invidious) failed: {(proc.stderr or '')[:200]}"
        # Move to dest
        try: shutil.move(tmp_src, str(dest))
        except OSError:
            shutil.copy(tmp_src, str(dest))
            Path(tmp_src).unlink(missing_ok=True)
        self._emit(tid, self.P_CONVERT_DONE)
        return str(dest), None

    # ====================================================================
    # v16.6 STRATEGY 5: SAPISIDHASH Innertube direct /youtubei/v1/player
    # ====================================================================
    def _try_innertube(self, ffmpeg, video_id, dest, tid):
        """Strategy 5: call YouTube's internal /youtubei/v1/player API directly
        with SAPISIDHASH auth + 5-client-type rotation. Reverse-engineered from
        JustAnotherMusicClient lib.rs lines 1507-1648 + tauriFetch.ts lines 92-128.
        Requires the user to have set up yt_cookies_str (raw cookie header with
        SAPISID / __Secure-1PAPISID / __Secure-3PAPISID)."""
        if self._auth_strategy not in ("auto", "innertube"):
            return None, "skipped (auth_strategy != innertube/auto)"
        if not self._cookies_str:
            return None, "no SAPISID cookie configured (use Settings → YouTube Auth)"
        print(f"[Aurora][Browse] Strategy 5: Innertube direct API (5-client rotation)", flush=True)
        self._emit(tid, 10)
        # Parse SAPISID from cookie string
        sapisid = None
        for part in self._cookies_str.split(";"):
            kv = part.strip().split("=", 1)
            if len(kv) == 2 and kv[0].strip() in ("SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID"):
                sapisid = kv[1].strip(); break
        if not sapisid:
            return None, "no SAPISID in cookie string"
        # Try each of the 5 client types in order
        for client_name, client_version, user_agent, x_cn in INNERTUBE_CLIENTS:
            try:
                audio_url = self._innertube_player_api(video_id, client_name,
                    client_version, user_agent, x_cn, sapisid)
                if not audio_url: continue
                print(f"[Aurora][Browse] Innertube {client_name} returned audio URL", flush=True)
                self._emit(tid, 50)
                # ffmpeg → MP3
                tmp_src = str(MUSIC_FOLDER / ".aurora-tmp" / f"innertube_{tid}_{client_name}.src")
                Path(tmp_src).parent.mkdir(parents=True, exist_ok=True)
                cmd_ff = [ffmpeg, "-y", "-i", audio_url, "-vn", "-acodec", "libmp3lame",
                          "-q:a", "2", "-user_agent", user_agent, tmp_src]
                try:
                    proc = subprocess.run(cmd_ff, capture_output=True, text=True,
                                          timeout=180, check=False)
                except subprocess.TimeoutExpired:
                    continue
                if proc.returncode != 0 or not Path(tmp_src).exists():
                    continue
                try: shutil.move(tmp_src, str(dest))
                except OSError:
                    shutil.copy(tmp_src, str(dest))
                    Path(tmp_src).unlink(missing_ok=True)
                self._emit(tid, self.P_CONVERT_DONE)
                return str(dest), None
            except Exception as e:
                print(f"[Aurora][Browse] Innertube {client_name} failed: {e}", flush=True)
                continue
        return None, "all 5 Innertube client types failed"
    def _innertube_player_api(self, video_id, client_name, client_version, user_agent, x_cn, sapisid):
        """Call /youtubei/v1/player with the given client context. Returns
        audio URL or None. Ported from JustAnotherMusicClient lib.rs lines 1650-1998."""
        import time as _time, hashlib
        ts = int(_time.time())
        origin = "https://music.youtube.com" if client_name == "web_remix" else "https://www.youtube.com"
        # SAPISIDHASH = SHA1("{timestamp} {sapisid} {origin}")
        sapisid_hash = hashlib.sha1(f"{ts} {sapisid} {origin}".encode()).hexdigest()
        auth_header = f"SAPISIDHASH {ts}_{sapisid_hash}"
        api_url = (INNERTUBE_MUSIC_PLAYER_URL if client_name == "web_remix"
                   else INNERTUBE_PLAYER_URL) + f"?key={INNERTUBE_API_KEY}&prettyPrint=false"
        # Build request body with client context
        body = {
            "videoId": video_id,
            "context": {
                "client": {
                    "clientName": x_cn,
                    "clientVersion": client_version,
                    "originalUrl": origin,
                }
            }
        }
        # For mobile clients, add platform info
        if client_name == "ios":
            body["context"]["client"].update({
                "deviceMake": "Apple", "deviceModel": "iPhone10,4",
                "osName": "iOS", "osVersion": "16.7.7",
            })
        elif client_name == "android":
            body["context"]["client"].update({
                "deviceMake": "Samsung", "deviceModel": "SM-S908E",
                "osName": "Android", "osVersion": "16",
            })
        headers = {
            "Content-Type": "application/json",
            "User-Agent": user_agent,
            "X-YouTube-Client-Name": x_cn,
            "X-YouTube-Client-Version": client_version,
            "Referer": origin + "/",
            "Origin": origin,
            "Authorization": auth_header,
            "X-Goog-Request-Time": str(ts),
            "Cookie": self._cookies_str,
        }
        try:
            req = _urlreq.Request(api_url, data=json.dumps(body).encode(),
                                  headers=headers, method="POST")
            with _urlreq.urlopen(req, timeout=20) as r:
                resp = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            print(f"[Aurora][Browse] Innertube API call failed: {e}", flush=True)
            return None
        # Extract best-audio URL from streamingData.formats / adaptiveFormats
        streaming = resp.get("streamingData") or {}
        candidates = []
        for f in (streaming.get("adaptiveFormats") or []):
            mime = (f.get("mimeType") or "").lower()
            if "audio" in mime and f.get("url"):
                candidates.append((int(f.get("bitrate", 0) or 0), f["url"]))
        # Sort by bitrate desc, return highest
        if not candidates: return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    # ====================================================================
    # v16.6 STRATEGY 6: Plain yt-dlp (last resort — no auth)
    # ====================================================================
    def _try_plain_ytdlp(self, ytdlp, watch_url, out_tmpl, tid):
        """Strategy 6: plain yt-dlp, no auth. Works for videos that YouTube
        hasn't bot-protected (typically less popular uploads)."""
        print(f"[Aurora][Browse] Strategy 6: plain yt-dlp (no auth)", flush=True)
        cmd = [ytdlp, "--no-warnings", "--no-playlist", "--no-progress", "--newline",
               "--extract-audio", "--audio-format", "mp3", "--audio-quality", "2",
               "-o", out_tmpl, "--print", "after_move:filepath", watch_url]
        return self._run_ytdlp_download(cmd, tid, "plain-ytdlp")

    def _run_ytdlp_download(self, cmd, tid, strategy_name):
        """Shared yt-dlp download runner for strategies 1/2/3/6. Returns
        (final_path, error) — error is None on success. If the error is
        bot-detection, returns (None, "bot-blocked") so the caller knows to
        try the next strategy."""
        import threading
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=self._subprocess_env())
        final_path = None
        stderr_lines = []
        def _read_stderr():
            try:
                for ln in proc.stderr:
                    stderr_lines.append(ln)
                    if "[download]" in ln and "%" in ln:
                        try:
                            pct_str = ln.split("%")[0].split()[-1]
                            pct = float(pct_str)
                            mapped = int(self.P_SEARCH_DONE + (pct / 100.0) *
                                         (self.P_DOWNLOAD_MAX - self.P_SEARCH_DONE))
                            self._emit(tid, mapped)
                        except (ValueError, IndexError): pass
            except Exception: pass
        t_read = threading.Thread(target=_read_stderr, daemon=True)
        t_read.start()
        for ln in proc.stdout:
            ln = ln.strip()
            if ln and not ln.startswith("["):
                final_path = ln
        try: proc.wait(timeout=600)
        except subprocess.TimeoutExpired:
            proc.kill()
            return None, f"{strategy_name} timed out (10 min)"
        t_read.join(timeout=2)
        if proc.returncode != 0:
            stderr_text = "".join(stderr_lines)
            if self._is_bot_blocked(stderr_text):
                return None, "bot-blocked"
            err = stderr_text.strip().split("\n")[-1][:300]
            return None, f"{strategy_name} failed: {err}"
        if not final_path or not Path(final_path).exists():
            return None, f"{strategy_name} finished but no file found"
        return final_path, None

    def run(self):
        t = self._track
        if not t: return
        tid = t.track_id
        try:
            # ---- 0. Pre-flight checks ----
            ytdlp = self._find_ytdlp()
            if not ytdlp:
                self.done.emit(tid, "", False,
                    "yt-dlp not installed. Install with: pip install --break-system-packages yt-dlp")
                return
            ffmpeg = self._find_ffmpeg()
            if not ffmpeg:
                self.done.emit(tid, "", False,
                    "ffmpeg not installed. Install with: sudo apt install ffmpeg")
                return
            dest = MUSIC_FOLDER / t.safe_filename("mp3")
            # Idempotent: skip if already downloaded
            if dest.exists() and dest.stat().st_size > 10240:
                self._emit(tid, 100)
                self.done.emit(tid, str(dest), True, "already-exists")
                return
            # ---- 1. Search YouTube for "{artist} {title}" (best match) ----
            self._emit(tid, 1)
            search_q = t.search_query()
            print(f"[Aurora][Browse] yt-dlp search: {search_q!r}", flush=True)
            video_id, search_err = self._search_youtube(ytdlp, search_q)
            if not video_id:
                self.done.emit(tid, "", False, f"YouTube search failed: {search_err}")
                return
            print(f"[Aurora][Browse] picked video_id={video_id}", flush=True)
            self._emit(tid, self.P_SEARCH_DONE)
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            # ---- 2. Try each strategy in order ----
            tmp_dir = MUSIC_FOLDER / ".aurora-tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            stem = f"aurora_{tid}_{int(datetime.now().timestamp())}"
            out_tmpl = str(tmp_dir / f"{stem}.%(ext)s")
            # Strategy attempts: (callable, args, name)
            strategies = [
                (self._try_cookies_from_browser, (ytdlp, watch_url, out_tmpl, tid), "cookies-from-browser"),
                (self._try_cookies_file,          (ytdlp, watch_url, out_tmpl, tid), "cookies-file"),
                (self._try_client_rotation,       (ytdlp, watch_url, out_tmpl, tid), "client-rotation"),
                (self._try_invidious,             (ffmpeg, video_id, dest, tid),     "invidious"),
                (self._try_innertube,             (ffmpeg, video_id, dest, tid),     "innertube"),
                (self._try_plain_ytdlp,           (ytdlp, watch_url, out_tmpl, tid), "plain-ytdlp"),
            ]
            final_path = None
            winning_strategy = None
            last_error = "all strategies failed"
            for fn, args, name in strategies:
                if self._cancel: break
                try:
                    result, err = fn(*args)
                except Exception as e:
                    print(f"[Aurora][Browse] Strategy {name} crashed: {e}", flush=True)
                    result, err = None, str(e)
                if result:
                    final_path = result
                    winning_strategy = name
                    break
                else:
                    print(f"[Aurora][Browse] Strategy {name} failed: {err}", flush=True)
                    last_error = f"{name}: {err}"
                    continue
            if not final_path:
                self.done.emit(tid, "", False,
                    f"All download strategies failed. Last error: {last_error}. "
                    f"Open Settings → YouTube Auth to configure cookies or browser auth.")
                return
            # ---- 3. Move file to dest (if not already there from Invidious/Innertube) ----
            if winning_strategy in ("invidious", "innertube"):
                # These strategies wrote directly to dest already
                if not Path(final_path).exists():
                    self.done.emit(tid, "", False, f"File vanished after {winning_strategy}")
                    return
            else:
                mp3_path = Path(final_path)
                if mp3_path != dest:
                    if dest.exists():
                        i = 1
                        while True:
                            cand = dest.with_name(f"{dest.stem} ({i}).mp3")
                            if not cand.exists(): dest = cand; break
                            i += 1
                    try: shutil.move(str(mp3_path), str(dest))
                    except OSError:
                        shutil.copy(str(mp3_path), str(dest))
                        mp3_path.unlink(missing_ok=True)
            try: tmp_dir.rmdir()
            except OSError: pass
            self._emit(tid, self.P_CONVERT_DONE + 2)
            # ---- 4. Tag the MP3 with iTunes metadata + cover art ----
            try:
                _tag_mp3(dest, t)
            except Exception as e:
                print(f"[Aurora][Browse] mp3 tag skipped: {e}", flush=True)
            self._emit(tid, self.P_TAG_DONE)
            # Emit strategy_used so the UI can show which strategy worked
            self.strategy_used.emit(tid, winning_strategy)
            self.done.emit(tid, str(dest), True, f"strategy:{winning_strategy}")
        except Exception as e:
            print(f"[Aurora][Browse] download error: {e}", flush=True)
            self.done.emit(tid, "", False, f"Unexpected: {e}")

def _tag_mp3(path, track):
    """v16.5: Embed iTunes metadata into the downloaded .mp3 via mutagen.
    Cover art is downloaded from iTunes artwork_url at 600x600 and embedded
    as an APIC frame (ID3)."""
    if not HAS_MUTAGEN: return
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TDRC, APIC, ID3NoHeaderError
    try:
        try:
            audio = ID3(str(path))
        except ID3NoHeaderError:
            audio = ID3()
        # Strip any existing tags yt-dlp might have written so we replace cleanly
        audio.delall("TIT2"); audio.delall("TPE1"); audio.delall("TALB")
        audio.delall("TCON"); audio.delall("TDRC"); audio.delall("APIC")
        audio["TIT2"] = TIT2(encoding=3, text=track.title)
        audio["TPE1"] = TPE1(encoding=3, text=track.artist)
        if track.album: audio["TALB"] = TALB(encoding=3, text=track.album)
        if track.genre: audio["TCON"] = TCON(encoding=3, text=track.genre)
        if track.release_date:
            # ID3 TDRC expects YYYY or YYYY-MM-DD
            audio["TDRC"] = TDRC(encoding=3, text=track.release_date[:10])
        # Embed cover art (download from iTunes artwork_url at 600x600) — best-effort
        try:
            cover_url = track.artwork(600)
            if cover_url:
                with _urlreq.urlopen(_urlreq.Request(cover_url,
                                  headers={"User-Agent": "Aurora-Music/16.5"}), timeout=10) as r:
                    cover_bytes = r.read()
            if cover_bytes:
                audio["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3,
                                     desc="Cover", data=cover_bytes)
        except Exception as e:
            print(f"[Aurora][Browse] cover art skipped: {e}", flush=True)
        audio.save(str(path))
    except Exception as e:
        print(f"[Aurora][Browse] mp3 tag failed: {e}", flush=True)

# ============================================================================
# v16.0 — BrowseResultGrid: a single search-result card
# ============================================================================

class BrowseResultCard(QFrame):
    """v16.7: A single browse result card — thumbnail + title/artist + a SINGLE
    Download button (Preview button removed in v16.5 per user request). The
    Download button downloads the FULL track via yt-dlp + ffmpeg (not the
    30-second iTunes preview).

    v16.7 NEW: Double-click anywhere on the card (except the Download button)
    emits playRequested(track). The Win handler checks if the song is already
    downloaded — if yes, plays it immediately; if no, downloads it first then
    auto-plays when the download completes.

    Emits: downloadRequested(track), playRequested(track)."""
    downloadRequested = Signal(object)
    playRequested = Signal(object)  # v16.7: double-click to play
    CARD_W = 200
    def __init__(self, track, thumb_loader, parent=None):
        super().__init__(parent)
        self.track = track
        self.thumb_loader = thumb_loader
        self.setFrameShape(QFrame.NoFrame)
        self.setObjectName("browseCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.CARD_W, 280)  # v16.7: +20px for "Double-click to play" hint
        # v16.7: double-click on the card emits playRequested
        # (mouseDoubleClickEvent is overridden below)
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 12, 12, 14); lay.setSpacing(8)
        # Thumbnail (96x96 — bumped up to 168 for the grid card)
        self.thumb = QLabel(); self.thumb.setFixedSize(168, 168)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(f"background:{M3['surface_container_high']}; border-radius:12px;")
        # Loading placeholder (music-note SVG)
        ph = _svg_pixmap(IC_MUSIC, M3["outline_variant"], 64)
        self.thumb.setPixmap(ph)
        lay.addWidget(self.thumb, alignment=Qt.AlignCenter)
        # Title (elided)
        self.title_lbl = QLabel(track.title); self.title_lbl.setObjectName("browseTitle")
        self.title_lbl.setWordWrap(False); self.title_lbl.setToolTip(track.title)
        lay.addWidget(self.title_lbl)
        # Artist (elided)
        self.artist_lbl = QLabel(track.artist); self.artist_lbl.setObjectName("browseArtist")
        self.artist_lbl.setWordWrap(False); self.artist_lbl.setToolTip(track.artist)
        lay.addWidget(self.artist_lbl)
        # Duration + genre chip
        dur = fmt_time(track.duration_ms / 1000) if track.duration_ms else ""
        meta_parts = []
        if dur: meta_parts.append(dur)
        if track.genre: meta_parts.append(track.genre)
        meta_text = "  •  ".join(meta_parts) if meta_parts else "—"
        self.meta_lbl = QLabel(meta_text); self.meta_lbl.setObjectName("browseMeta")
        lay.addWidget(self.meta_lbl)
        # v16.5: SINGLE Download button — centered, full-width pill, no Preview.
        btn_row = QHBoxLayout(); btn_row.setSpacing(6); btn_row.setContentsMargins(0,2,0,0)
        self.download_btn = QPushButton("  Download"); self.download_btn.setObjectName("browseDownloadBtnWide")
        self.download_btn.setIcon(_svg(IC_DOWNLOAD, M3["on_primary"]))
        self.download_btn.setIconSize(QSize(16,16))
        self.download_btn.setFixedHeight(36)
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.setToolTip("Download full track to ~/Downloads/ (MP3, ~190kbps)")
        self.download_btn.clicked.connect(lambda: self.downloadRequested.emit(self.track))
        btn_row.addWidget(self.download_btn)
        lay.addLayout(btn_row)
        # v16.9: hint label — "Double-click for 30s preview"
        hint = QLabel("Double-click for 30s preview"); hint.setObjectName("browseHint")
        lay.addWidget(hint)
        # Kick off async thumbnail load
        self._load_thumb(track.artwork(300))
    def mouseDoubleClickEvent(self, event):
        """v16.7: double-click anywhere on the card (except the Download button)
        emits playRequested(track). The Download button handles its own clicks
        and doesn't propagate to this handler."""
        if event.button() == Qt.LeftButton:
            self.playRequested.emit(self.track)
        super().mouseDoubleClickEvent(event)
    def _load_thumb(self, url):
        def cb(pm):
            if pm and not pm.isNull():
                self.thumb.setPixmap(pm.scaled(168, 168, Qt.KeepAspectRatioByExpanding,
                                               Qt.SmoothTransformation))
        try:
            self.thumb_loader.load(url, cb, size=168)
        except Exception as e:
            print(f"[Aurora][Browse] thumb load failed: {e}", flush=True)
    def set_downloading(self, is_downloading, pct=0):
        """Visual state: download in progress (spinner) vs idle."""
        if is_downloading:
            self.download_btn.setIcon(_svg(IC_LOADING, M3["on_primary"]))
            self.download_btn.setToolTip(f"Downloading {pct}%")
        else:
            self.download_btn.setIcon(_svg(IC_DOWNLOAD, M3["on_primary"]))
            self.download_btn.setToolTip("Download to ~/Downloads/")
        self.download_btn.update()
    def set_downloaded(self, ok=True):
        """Visual state: completed (green check) or failed (red)."""
        if ok:
            self.download_btn.setIcon(_svg(IC_CHECK, M3["on_primary"]))
            self.download_btn.setToolTip("Downloaded — check Library")
        else:
            self.download_btn.setIcon(_svg(IC_DOWNLOAD, M3["on_primary"]))
            self.download_btn.setToolTip("Download failed — retry")
        self.download_btn.update()

# ===== Library Scanner =====
class Scanner(QThread):
    done = Signal(list)
    def run(self):
        songs=[]
        try:
            if not MUSIC_FOLDER.exists():
                MUSIC_FOLDER.mkdir(parents=True, exist_ok=True)
                self.done.emit([]); return
            # Sort by mtime (newest first); guard against stat() failures on deleted files
            file_list = []
            for fp in MUSIC_FOLDER.iterdir():
                try:
                    file_list.append((fp, fp.stat().st_mtime))
                except OSError:
                    continue
            file_list.sort(key=lambda x: x[1], reverse=True)
            for fp, _ in file_list:
                if fp.is_file() and fp.suffix.lower() in SUPPORTED:
                    try:
                        songs.append(get_metadata(fp))
                    except Exception as e:
                        print(f"[Aurora] Skipping {fp.name}: {e}", flush=True)
        except Exception as e:
            print(f"[Aurora] Scanner error: {e}", flush=True)
        # CRITICAL: done signal MUST fire even on error, otherwise UI stays
        # stuck on 'Scanning...' forever (this was a 'dumb loader' complaint).
        self.done.emit(songs)

# ===== MPRIS =====
class MprisCtrl:
    def __init__(self, win):
        self.win=win; self.server=None
        if not HAS_MPRIS or sys.platform!="linux": return
        try:
            from mpris_server.mpris.metadata import MetadataEntries
            from mpris_server.base import Track as MprisTrack, Album as MprisAlbum, Artist as MprisArtist
            class Adapter(MprisAdapter):
                def __init__(s,w): super().__init__(); s.w=w
                def get_playstate(s):
                    st=s.w.player.playbackState()
                    if st==QMediaPlayer.PlayingState: return PlayState.PLAYING
                    elif st==QMediaPlayer.PausedState: return PlayState.PAUSED
                    return PlayState.STOPPED
                def get_current_title(s): return s.w.cur["title"] if s.w.cur else ""
                def get_current_artists(s): return [s.w.cur["artist"]] if s.w.cur else []
                def get_current_album(s): return s.w.cur["album"] if s.w.cur else ""
                def get_current_art_url(s): return ""
                def get_current_track_id(s): return f"/aurora/{abs(hash(s.w.cur['path']))}" if s.w.cur else "/aurora/none"
                def get_current_length(s): return s.w.cur["duration"]*1000000 if s.w.cur and s.w.cur["duration"] else 0
                def get_volume(s): return s.w.audio.volume()
                def set_volume(s,v): s.w.remote_cmd.emit("volume",str(float(v)))  # v12.2: widgets must be touched on main thread
                def get_position(s): return int(s.w.player.position()*1000)
                def get_current_position(s): return int(s.w.player.position()*1000)
                def get_metadata(s):
                    d = {MetadataEntries.TRACK_ID: s.get_current_track_id()}
                    if s.w.cur:
                        d[MetadataEntries.LENGTH] = s.get_current_length()
                        d[MetadataEntries.TITLE] = s.get_current_title()
                        d[MetadataEntries.ARTISTS] = s.get_current_artists()
                        d[MetadataEntries.ALBUM] = s.get_current_album()
                    return d
                def get_current_track(s):
                    if not s.w.cur: return None
                    return MprisTrack(
                        track_id=s.get_current_track_id(),
                        length=s.get_current_length(),
                        name=s.get_current_title(),
                        artists=[MprisArtist(name=a) for a in s.get_current_artists()],
                        album=MprisAlbum(name=s.get_current_album()) if s.get_current_album() else None
                    )
                def can_control(s): return True
                def can_play(s): return True
                def can_pause(s): return True
                def can_go_next(s): return True
                def can_go_previous(s): return True
                def can_seek(s): return True
                def is_mute(s): return s.w.audio.isMuted()
                def is_playlist(s): return s.w.repeat==RepeatMode.ALL
                def is_repeating(s): return s.w.repeat!=RepeatMode.OFF
                def get_shuffle(s): return s.w.shuffle
                def get_rate(s): return 1.0
                def get_minimum_rate(s): return 0.5
                def get_maximum_rate(s): return 2.0
                def get_art_url(s,t): return ""
                def get_stream_title(s): return s.w.cur["title"] if s.w.cur else ""
                # CRITICAL FIX v12.2: MPRIS calls arrive on the GLib background
                # thread (see loop(background=True) below). Calling QMediaPlayer /
                # widget methods directly from that thread is undefined behavior:
                # commands silently no-op or crash. This is why playerctl
                # play/pause/stop "did nothing" for the agent. All commands are
                # now marshalled to the Qt main thread via a queued signal.
                def play(s): s.w.remote_cmd.emit("play","")
                def pause(s): s.w.remote_cmd.emit("pause","")
                def play_pause(s): s.w.remote_cmd.emit("toggle","")
                def stop(s): s.w.remote_cmd.emit("stop","")
                def next(s): s.w.remote_cmd.emit("next","")
                def previous(s): s.w.remote_cmd.emit("prev","")
                def seek(s,o): s.w.remote_cmd.emit("seek",str(o//1000))
                def set_position(s,t,p): s.w.remote_cmd.emit("setpos",str(p//1000))
                def open_uri(s,u):
                    if u.startswith("file://"): s.w.remote_cmd.emit("play-file",u[7:])
            self.server=Server(APP_DBUS,Adapter(win))
            # CRITICAL FIX v12.1: loop() defaults to background=False which BLOCKS
            # the calling thread forever. Called from Win.__init__, this froze the
            # entire Qt event loop -> no UI, no scanner, no IPC, no playerctl.
            # Run the GLib MainLoop in a daemon thread so Qt can run in main thread.
            self.server.loop(background=True)
            print(f"[Aurora] MPRIS: org.mpris.MediaPlayer2.{APP_DBUS}", flush=True)
        except Exception as e: print(f"[Aurora] MPRIS fail: {e}", flush=True)
    def update(self):
        if self.server:
            try: self.server.emit_properties_changed()
            except: pass

# ===== Main Window =====
class Win(QMainWindow):
    # v12.2: queued cross-thread bridge for MPRIS/agent commands (cmd, arg)
    remote_cmd = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME); self.setMinimumSize(800,550)
        self.cfg=load_cfg(); self.resize(self.cfg.get("w",1100),self.cfg.get("h",750))
        self.songs=[]; self.cur_idx=-1; self.cur=None; self.playing=False
        self.repeat=RepeatMode.OFF; self.shuffle=self.cfg.get("shuffle",False)
        self.sort=SortMode.DATE; self.queue=[]; self.qidx=0
        self.playlists=load_pl()
        if self.cfg.get("repeat")=="all": self.repeat=RepeatMode.ALL
        elif self.cfg.get("repeat")=="one": self.repeat=RepeatMode.ONE
        self.player=QMediaPlayer(); self.audio=QAudioOutput(); self.player.setAudioOutput(self.audio)
        self.audio.setVolume(self._curve(self.cfg.get("vol",70)))  # v13: perceptual curve
        # v12.3: audio output device selector support
        # Keep persistent QMediaDevices instance so audioOutputsChanged works
        # (a temporary instance gets garbage-collected and the signal dies).
        self._media_devices = QMediaDevices()
        self._media_devices.audioOutputsChanged.connect(self._on_audio_devices_changed)
        self._test_player = None  # holds test-tone player so repeated tests don't overlap
        saved_device_id = self.cfg.get("audio_device_id")
        if saved_device_id:
            try:
                import base64
                target_id = base64.b64decode(saved_device_id)
                for d in QMediaDevices.audioOutputs():
                    if bytes(d.id()) == target_id:
                        self.audio.setDevice(d)
                        break
            except Exception:
                pass  # device not connected yet - fall back to default, never crash
        self.player.positionChanged.connect(self._pos); self.player.durationChanged.connect(self._dur)
        self.player.mediaStatusChanged.connect(self._status)
        # v17.5: REAL-TIME AUDIO SYNC — QAudioBufferOutput gives us live decoded
        # audio buffers from QMediaPlayer as the song plays. We compute FFT on
        # each buffer and feed the spectrum to the Visualizer. This makes the
        # bars literally move with the actual audio output (like CAVA does).
        self._setup_audio_buffer_output()
        self._build(); self._shortcuts(); self._tray()
        # v12.2: keep play/pause icon + status file in sync with the REAL
        # playback state (the old self.playing flag drifted out of sync,
        # e.g. after EndOfMedia, making the toggle button do the wrong thing).
        self.player.playbackStateChanged.connect(self._state_changed)
        # v12.2: execute remote (MPRIS/playerctl) commands on the main thread.
        self.remote_cmd.connect(self._on_remote_cmd)
        # v15: async beat-graph level scanner + EQ-badge repaint ticker
        self.lv_scanner=LevelScanner(self); self.lv_scanner.done.connect(self._levels_done)
        self.eq_timer=QTimer(self); self.eq_timer.setInterval(120); self.eq_timer.timeout.connect(self._eq_tick)
        self.mpris=MprisCtrl(self); self.scan()
        # v14: auto-rescan every 10 min (was 30 s — wasteful on a Celeron);
        # there is now a manual Refresh button + F5 for instant rescans.
        self.rt=QTimer(); self.rt.timeout.connect(self.scan); self.rt.start(600000)
        self.ct=QTimer(); self.ct.timeout.connect(self._check_cmd); self.ct.start(500)
        # v16.8: session time tracking — load session (resets session_started on launch)
        # and save it every 30 seconds so total_app_seconds accumulates.
        self._session = load_session()
        self._session_timer = QTimer(self)
        self._session_timer.setInterval(30000)  # save every 30s
        self._session_timer.timeout.connect(self._save_session_time)
        self._session_timer.start()

    def _build(self):
        c=Backdrop(); self.backdrop=c; self.setCentralWidget(c); ml=QHBoxLayout(c); ml.setContentsMargins(0,0,0,0); ml.setSpacing(0)
        # Sidebar
        sb=QFrame(); sb.setObjectName("sidebar"); sb.setFixedWidth(220)
        sl=QVBoxLayout(sb); sl.setContentsMargins(0,0,0,0); sl.setSpacing(0)
        t=QLabel("Aurora"); t.setStyleSheet(f"font-size:22px;font-weight:500;color:{M3['primary']};padding:24px 20px 4px;background:transparent;"); sl.addWidget(t)
        self._sidebar_title=t  # v15: restyled on retheme
        st=QLabel("Music Player"); st.setStyleSheet(f"font-size:12px;color:{M3['on_surface_variant']};padding:0 20px 24px;background:transparent;"); sl.addWidget(st)
        self.navs={}  # v16: Browse added back as a real page (was just a header in v14)
        # v16: Browse sits between Library and Playlists — it's the discovery
        # entry-point (online iTunes search + 1-click download).
        # v16.8: History sits between Browse and Playlists — shows last 100
        # played songs with date/time/play-count + session/total-time stats.
        for k,txt,ic in [("library","Library",IC_LIST),("browse","Browse",IC_BROWSE),
                         ("history","History",IC_HISTORY),
                         ("equalizer","Equalizer",IC_EQUALIZER),
                         ("playlists","Playlists",IC_LIST),("queue","Queue",IC_LIST),
                         ("settings","Settings",IC_SETTINGS)]:
            b=QPushButton("  "+txt); b.setObjectName("navButton"); b.setCheckable(True)
            b.setIcon(_svg(ic, M3["on_surface_variant"]))
            b.setIconSize(QSize(18,18))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _,kk=k: self._switch(kk)); sl.addWidget(b); self.navs[k]=b
        self.navs["library"].setChecked(True); sl.addStretch()
        v=QLabel(f"v{APP_VERSION}"); v.setStyleSheet(f"font-size:11px;color:{M3['outline']};padding:16px 20px;background:transparent;"); v.setAlignment(Qt.AlignCenter); sl.addWidget(v)
        ml.addWidget(sb)
        # Content
        content=QFrame(); content.setObjectName("contentArea")
        cl=QVBoxLayout(content); cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)
        self.stack=QStackedWidget()
        # v16: Browse inserted at index 1 (between Library and Playlists).
        # v16.8: History inserted at index 2 (between Browse and Playlists).
        # v17.0: Equalizer inserted at index 3 (between History and Playlists).
        # Stack order MUST stay in sync with _switch().
        self.stack.addWidget(self._lib_view())       # index 0
        self.stack.addWidget(self._browse_view())     # index 1 — v16
        self.stack.addWidget(self._history_view())    # index 2 — v16.8
        self.stack.addWidget(self._equalizer_view())  # index 3 — v17.0
        self.stack.addWidget(self._pl_view())         # index 4
        self.stack.addWidget(self._q_view())          # index 5
        self.stack.addWidget(self._settings_view())   # index 6
        cl.addWidget(self.stack)
        # v15: SoundCloud-style beat graph above the player bar
        self.viz=Visualizer(self); self.viz.setVisible(bool(self.cfg.get("show_viz",True)))
        cl.addWidget(self.viz)
        # Player bar
        pb=QFrame(); pb.setObjectName("playerBar"); pb.setFixedHeight(100)
        pl=QHBoxLayout(pb); pl.setContentsMargins(24,14,24,14); pl.setSpacing(16)
        self.art=QLabel(""); self.art.setObjectName("albumArt"); self.art.setAlignment(Qt.AlignCenter)
        self.art.setStyleSheet(f"font-size:11px;color:{M3['on_surface_variant']};"); pl.addWidget(self.art)
        il=QVBoxLayout(); il.setSpacing(2)
        # v17.0: AnimatedNowPlaying widget (pulsing dot + dancing bars)
        # sits above the title to show playback state with motion graphics
        self.now_playing_anim = AnimatedNowPlaying(self)
        self.now_playing_anim.win = self
        il.addWidget(self.now_playing_anim)
        # v14: ElideLabel + Ignored horizontal policy — long titles now elide
        # with "..." instead of squeezing the control buttons (resize glitch fix)
        self.tl=ElideLabel("No song selected"); self.tl.setObjectName("titleLabel")
        self.tl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred); il.addWidget(self.tl)
        self.al=ElideLabel("Select a song from the library"); self.al.setObjectName("artistLabel")
        self.al.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred); il.addWidget(self.al)
        self.tl.setMinimumWidth(160); self.al.setMinimumWidth(160)
        # v17.5: A-B Loop buttons — two small buttons below the song title.
        # Click A to mark start point, click B to mark end point.
        # Song loops between A and B until song changes.
        # A and B persist for the current song only — changing song resets them.
        ab_row = QHBoxLayout(); ab_row.setSpacing(6); ab_row.setContentsMargins(0,0,0,0)
        self.ab_a_btn = QPushButton(" A"); self.ab_a_btn.setObjectName("abButton")
        self.ab_a_btn.setFixedSize(32, 22); self.ab_a_btn.setCursor(Qt.PointingHandCursor)
        self.ab_a_btn.setToolTip("Set A point (loop start) — click while playing")
        self.ab_a_btn.setCheckable(True)
        self.ab_a_btn.clicked.connect(lambda: self._ab_set("A"))
        ab_row.addWidget(self.ab_a_btn)
        self.ab_b_btn = QPushButton(" B"); self.ab_b_btn.setObjectName("abButton")
        self.ab_b_btn.setFixedSize(32, 22); self.ab_b_btn.setCursor(Qt.PointingHandCursor)
        self.ab_b_btn.setToolTip("Set B point (loop end) — click while playing")
        self.ab_b_btn.setCheckable(True)
        self.ab_b_btn.clicked.connect(lambda: self._ab_set("B"))
        ab_row.addWidget(self.ab_b_btn)
        self.ab_clear_btn = QPushButton("Clear"); self.ab_clear_btn.setObjectName("abClearBtn")
        self.ab_clear_btn.setFixedSize(50, 22); self.ab_clear_btn.setCursor(Qt.PointingHandCursor)
        self.ab_clear_btn.setToolTip("Clear A-B loop")
        self.ab_clear_btn.clicked.connect(self._ab_clear)
        ab_row.addWidget(self.ab_clear_btn)
        ab_row.addStretch()
        il.addLayout(ab_row)
        # A-B state
        self._ab_a = None  # position in ms, or None
        self._ab_b = None  # position in ms, or None
        self._ab_looping = False
        pl.addLayout(il,stretch=2)
        # Controls
        cl2=QHBoxLayout(); cl2.setSpacing(4); cl2.setAlignment(Qt.AlignCenter)
        # v14: fixed sizes on ALL control buttons — they can no longer be
        # squeezed/overlapped when the window is resized small.
        self.sh=AnimatedButton(""); self.sh.setIcon(_svg(IC_SHUFFLE)); self.sh.setObjectName("controlButton"); self.sh.setCheckable(True); self.sh.setChecked(self.shuffle); self.sh.setToolTip("Shuffle"); self.sh.clicked.connect(self._shuf); self.sh.setFixedSize(40,40); cl2.addWidget(self.sh)
        self.pb_btn=AnimatedButton(""); self.pb_btn.setIcon(_svg(IC_PREV)); self.pb_btn.setObjectName("controlButton"); self.pb_btn.setToolTip("Previous"); self.pb_btn.clicked.connect(self.prev); self.pb_btn.setFixedSize(40,40); cl2.addWidget(self.pb_btn)
        self.pp=AnimatedButton(""); self._pi=_svg(IC_PLAY, M3["on_primary_container"]); self._ai=_svg(IC_PAUSE, M3["on_primary_container"]); self.pp.setIcon(self._pi); self.pp.setObjectName("playButton"); self.pp.setToolTip("Play/Pause"); self.pp.clicked.connect(self.toggle); self.pp.setFixedSize(56,56); cl2.addWidget(self.pp)
        self.nx=AnimatedButton(""); self.nx.setIcon(_svg(IC_NEXT)); self.nx.setObjectName("controlButton"); self.nx.setToolTip("Next"); self.nx.clicked.connect(self.next); self.nx.setFixedSize(40,40); cl2.addWidget(self.nx)
        self.rp=AnimatedButton(""); self.rp.setIcon(_svg(IC_REPEAT)); self.rp.setObjectName("controlButton"); self.rp.setToolTip("Repeat"); self.rp.clicked.connect(self._rep); self.rp.setFixedSize(40,40); cl2.addWidget(self.rp)
        pl.addLayout(cl2)
        # Seek
        sl2=QVBoxLayout(); sl2.setSpacing(4)
        # v15: ClickSlider — clicking anywhere on the bar seeks there (bug fix)
        self.seek=ClickSlider(Qt.Horizontal); self.seek.setRange(0,0); self.seek.setMinimumWidth(90); self.seek.sliderMoved.connect(lambda p: self.player.setPosition(p)); sl2.addWidget(self.seek)
        tl2=QHBoxLayout(); self.ct2=QLabel("0:00"); self.ct2.setObjectName("timeLabel"); tl2.addWidget(self.ct2); tl2.addStretch(); self.tt=QLabel("0:00"); self.tt.setObjectName("timeLabel"); tl2.addWidget(self.tt); sl2.addLayout(tl2)
        pl.addLayout(sl2,stretch=2)
        # Volume
        vl=QHBoxLayout(); vl.setSpacing(6)
        vb=QPushButton(""); vb.setIcon(_svg(IC_VOL)); vb.setObjectName("controlButton"); vb.setFixedSize(40,40); vl.addWidget(vb)  # M3: 40dp icon button
        vb.setToolTip("Mute"); vb.setCursor(Qt.PointingHandCursor); vb.clicked.connect(self._mute_toggle)  # v15: mute button now works
        self.vol=ClickSlider(Qt.Horizontal); self.vol.setObjectName("volumeSlider"); self.vol.setRange(0,100); self.vol.setValue(self.cfg.get("vol",70)); self.vol.setMinimumWidth(60); self.vol.setMaximumWidth(90); self.vol.valueChanged.connect(self._vol); vl.addWidget(self.vol)
        self.vol_btn=vb
        # v12.3: audio output device selector button
        self.dev_btn = QPushButton(""); self.dev_btn.setIcon(_svg(IC_AUDIO_DEVICE)); self.dev_btn.setObjectName("controlButton")
        self.dev_btn.setFixedSize(40,40); self.dev_btn.setToolTip("Audio Output Device")  # M3: 40dp icon button
        self.dev_btn.clicked.connect(self._show_device_selector); vl.addWidget(self.dev_btn)
        # v16: EXTERNAL BROWSE BUTTON — always visible in the player bar so the
        # user can jump to Browse (online search + 1-click download) from ANY
        # page with a single click. Filled primary-container button (M3 spec).
        self.browse_btn = AnimatedButton(""); self.browse_btn.setObjectName("externalBrowseBtn")
        self.browse_btn.setIcon(_svg(IC_BROWSE, M3["on_primary_container"]))
        self.browse_btn.setIconSize(QSize(20,20))
        self.browse_btn.setFixedSize(48,48); self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.setToolTip("Browse music online (v16) — search, preview, download")
        self.browse_btn.clicked.connect(lambda: self._switch("browse"))
        vl.addWidget(self.browse_btn)
        pl.addLayout(vl)
        # Combine
        # CRITICAL FIX v12.2: 'content' already owns layout 'cl' (created above
        # with the stack inside). The old code built a SECOND layout and called
        # content.setLayout(wrap), which Qt REJECTS ("widget already has a
        # layout") — leaving the entire player bar (play/pause/stop/next/seek/
        # volume) orphaned and INVISIBLE. That's why the user "could not use
        # or play anything" from the app. Just add the bar to the existing layout.
        cl.addWidget(pb)
        ml.addWidget(content,stretch=1)

    # v14: responsive player bar — on narrow windows, progressively hide the
    # lowest-priority controls instead of letting Qt squeeze/overlap them.
    # (Pattern reverse-engineered from FLB/Harmonoid mobile layouts.)
    def resizeEvent(self, e):
        super().resizeEvent(e)
        w = self.width()
        if hasattr(self, "sh"):
            for b in (self.sh, self.rp): b.setVisible(w >= 1040)      # shuffle/repeat
            for x in (self.vol, self.vol_btn, self.dev_btn): x.setVisible(w >= 960)  # volume group
            # v16: external Browse button stays visible down to 720px (it's
            # a primary discovery entry-point — should be hard to hide).
            if hasattr(self, "browse_btn"): self.browse_btn.setVisible(w >= 720)
            self.art.setVisible(w >= 900)                              # album art

    def _lib_view(self):
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        t=QLabel("Library"); t.setObjectName("pageTitle"); l.addWidget(t)
        self.sub=QLabel("Scanning ~/Downloads/..."); self.sub.setObjectName("pageSubtitle"); l.addWidget(self.sub)
        bar=QHBoxLayout(); bar.setContentsMargins(28,0,28,12)
        self.srch=QLineEdit(); self.srch.setObjectName("searchBar"); self.srch.setPlaceholderText("Search songs, artists, albums..."); self.srch.textChanged.connect(self._refresh); bar.addWidget(self.srch,stretch=1)
        self.sortc=QComboBox(); self.sortc.setObjectName("sortCombo"); self.sortc.addItems(["Date Added","Title","Artist","Album"]); self.sortc.currentIndexChanged.connect(self._sortc); bar.addWidget(self.sortc)
        # v14: manual Refresh button — instant rescan, no waiting for the timer
        rb=QPushButton(""); rb.setIcon(_svg(IC_REFRESH)); rb.setObjectName("controlButton")
        rb.setFixedSize(40,40); rb.setToolTip("Refresh library (F5)"); rb.setCursor(Qt.PointingHandCursor)
        rb.clicked.connect(self.scan); bar.addWidget(rb)
        l.addLayout(bar)
        self.slist=QListWidget(); self.slist.setObjectName("songList"); self.slist.itemDoubleClicked.connect(self._click); self.slist.setContextMenuPolicy(Qt.CustomContextMenu); self.slist.customContextMenuRequested.connect(self._ctx)
        # v13: rich FLB-style rows (thumb + title/artist + duration + accent pill)
        self.track_delegate=TrackDelegate(self); self.slist.setItemDelegate(self.track_delegate)
        self.slist.setMouseTracking(True); self.slist.setUniformItemSizes(True)
        l.addWidget(self.slist)
        return w

    # ====================================================================
    # v16.0 — BROWSE VIEW (online search + suggestions + preview + download)
    # ====================================================================
    def _browse_view(self):
        """iTunes-backed browse page: search bar with live auto-suggestions,
        results grid (cards with thumbnail + title + artist + 30s Preview +
        one-click Download). Random suggestions shown when search is empty."""
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        t=QLabel("Browse"); t.setObjectName("pageTitle"); l.addWidget(t)
        self.browse_sub=QLabel("Search iTunes — preview 30s, then download in one click")
        self.browse_sub.setObjectName("pageSubtitle"); l.addWidget(self.browse_sub)
        # --- Search bar row ---
        bar=QHBoxLayout(); bar.setContentsMargins(28,0,28,12); bar.setSpacing(8)
        self.browse_search=QLineEdit(); self.browse_search.setObjectName("searchBar")
        self.browse_search.setPlaceholderText("Search songs, artists, albums on iTunes...")
        self.browse_search.textChanged.connect(self._on_browse_text_changed)
        self.browse_search.returnPressed.connect(self._on_browse_return)
        bar.addWidget(self.browse_search,stretch=1)
        # Country picker (US/IN/GB/CA/AU/DE/FR/JP) — affects iTunes storefront
        self.browse_country=QComboBox(); self.browse_country.setObjectName("sortCombo")
        for code,name in [("US","US"),("IN","IN"),("GB","GB"),("CA","CA"),
                          ("AU","AU"),("DE","DE"),("FR","FR"),("JP","JP")]:
            self.browse_country.addItem(name, code)
        saved_country = self.cfg.get("browse_country", "US")
        idx = max(0, self.browse_country.findData(saved_country))
        self.browse_country.setCurrentIndex(idx)
        self.browse_country.currentIndexChanged.connect(self._on_browse_country_changed)
        self.browse_country.setToolTip("iTunes storefront region")
        bar.addWidget(self.browse_country)
        # Clear button
        cb=QPushButton(""); cb.setIcon(_svg(IC_CLOSE)); cb.setObjectName("controlButton")
        cb.setFixedSize(40,40); cb.setToolTip("Clear"); cb.setCursor(Qt.PointingHandCursor)
        cb.clicked.connect(lambda: self.browse_search.clear())
        bar.addWidget(cb)
        l.addLayout(bar)
        # --- Suggestions strip (horizontal pill list, shown while typing) ---
        self.browse_suggest_strip=QHBoxLayout(); self.browse_suggest_strip.setContentsMargins(28,0,28,8)
        self.browse_suggest_strip.setSpacing(6)
        self.browse_suggest_lbl=QLabel(""); self.browse_suggest_lbl.setObjectName("browseSuggestLabel")
        self.browse_suggest_strip.addWidget(self.browse_suggest_lbl)
        self.browse_suggest_pills_layout = self.browse_suggest_strip  # keep ref for retheme
        # We'll pack pills into a QWidget that we add to the strip
        self.browse_suggest_host = QWidget(); self.browse_suggest_host.setObjectName("suggestHost")
        sh_layout = QHBoxLayout(self.browse_suggest_host); sh_layout.setContentsMargins(0,0,0,0)
        sh_layout.setSpacing(6); sh_layout.addStretch()
        self.browse_suggest_strip.addWidget(self.browse_suggest_host, stretch=1)
        l.addLayout(self.browse_suggest_strip)
        # --- Status / progress bar ---
        stat_row = QHBoxLayout(); stat_row.setContentsMargins(28,4,28,8); stat_row.setSpacing(8)
        self.browse_status=QLabel("Type to search — random picks below")
        self.browse_status.setObjectName("browseStatus")
        stat_row.addWidget(self.browse_status, stretch=1)
        self.browse_progress=QProgressBar(); self.browse_progress.setFixedHeight(6)
        self.browse_progress.setRange(0,100); self.browse_progress.setValue(0)
        self.browse_progress.setTextVisible(False)
        self.browse_progress.setVisible(False)
        self.browse_progress.setObjectName("browseProgress")
        stat_row.addWidget(self.browse_progress, stretch=1)
        l.addLayout(stat_row)
        # --- Results grid (scrollable, wraps BrowseResultCard widgets) ---
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("browseScroll")
        # v16.5: wire scroll-position detection for infinite scroll
        scroll.verticalScrollBar().valueChanged.connect(self._on_browse_scroll)
        grid_host=QWidget(); grid_host.setObjectName("browseGrid")
        self.browse_grid=QGridLayout(grid_host)
        self.browse_grid.setContentsMargins(28,8,28,24); self.browse_grid.setSpacing(14)
        # v16.9: center the grid horizontally so there's no empty space on the
        # right side when the window is wider than the cards. (was: AlignLeft)
        self.browse_grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        scroll.setWidget(grid_host)
        # v16.9: make the grid_host expand to fill the scroll area width so
        # the HCenter alignment actually centers (otherwise the grid stays
        # at its minimumSizeHint width and left-aligns anyway).
        grid_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.browse_scroll = scroll  # keep ref for scroll-position queries
        l.addWidget(scroll, stretch=1)
        # --- State init ---
        self._browse_results=[]          # list[BrowseTrack] currently shown (rendered)
        self._browse_request_id=0        # race guard for stale search responses
        self._browse_suggest_id=0        # race guard for stale suggest responses
        # v16.5: infinite-scroll state
        self._browse_all_results=[]      # full buffer of fetched tracks (up to 200)
        self._browse_has_more=False      # True if buffer has un-rendered tracks
        self._browse_loading_more=False  # True while rendering the next page
        self._browse_last_query=""       # the query that produced the current results
        self._browse_last_country="US"   # the country that produced the current results
        # v16.7: pending-search queue — if the fetcher is busy when the user
        # types a new query, we store it here and fire it when the fetcher
        # finishes. This fixes the "search doesn't work, shows random stuff"
        # bug where the seed query's results would override the user's search.
        self._browse_pending_search=None  # (query, country) tuple or None
        # v16.7: auto-play after download — set by _browse_play() when the user
        # double-clicks a card that hasn't been downloaded yet. When the
        # download completes, _on_browse_dl_done checks this and plays the file.
        self._browse_autoplay_id=None
        self._browse_debounce=QTimer(self); self._browse_debounce.setSingleShot(True)
        self._browse_debounce.setInterval(BROWSE_DEBOUNCE_MS)
        self._browse_debounce.timeout.connect(self._fire_browse_search)
        self._browse_suggest_debounce=QTimer(self); self._browse_suggest_debounce.setSingleShot(True)
        self._browse_suggest_debounce.setInterval(BROWSE_DEBOUNCE_MS)
        self._browse_suggest_debounce.timeout.connect(self._fire_browse_suggest)
        # Background workers
        self._browse_fetcher=BrowseFetcher(self)
        self._browse_fetcher.done.connect(self._on_browse_results)
        self._suggest_fetcher=SuggestFetcher(self)
        self._suggest_fetcher.done.connect(self._on_browse_suggest)
        self._thumb_loader=ThumbnailLoader(self)
        self._downloader=Downloader(self)
        self._downloader.progress.connect(self._on_browse_dl_progress)
        self._downloader.done.connect(self._on_browse_dl_done)
        # v16.6: track which download strategy succeeded (shown in status bar)
        self._downloader.strategy_used.connect(self._on_browse_strategy_used)
        self._download_queue=[]          # list[BrowseTrack] — serialized by Downloader
        self._downloading_id=None        # track_id currently being downloaded
        # Trigger an initial "random picks" search on first show
        self._browse_initial_loaded = False
        QTimer.singleShot(200, self._browse_load_initial)
        return w

    def _browse_focus_search(self):
        """Called when user navigates to the Browse page — focus the search bar
        and trigger random picks if the field is empty (instant discovery)."""
        try:
            if hasattr(self, "browse_search"):
                self.browse_search.setFocus()
                if not self.browse_search.text().strip():
                    QTimer.singleShot(100, self._browse_load_initial)
        except Exception as e:
            print(f"[Aurora][Browse] focus failed: {e}", flush=True)

    def _browse_load_initial(self):
        """v16.7: load 'random suggestions' on first Browse visit. We pick from a
        COUNTRY-SPECIFIC curated list so country=IN shows Bollywood/Punjabi/Tamil
        content (not Taylor Swift). The country parameter only affects iTunes
        availability — we must use region-specific search terms to get regional
        content."""
        if self._browse_initial_loaded: return
        if self.browse_search.text().strip(): return  # user typed something — respect it
        self._browse_initial_loaded = True
        import random
        # v16.7: pick seeds based on the currently-selected country
        country = "US"
        try: country = self.browse_country.currentData() or "US"
        except Exception: pass
        seeds = BROWSE_SEED_QUERIES.get(country, BROWSE_SEED_QUERIES_DEFAULT)
        seed = random.choice(seeds)
        self.browse_search.setText(seed)
        self.browse_search.selectAll()
        # Fire search immediately (debounce timer will trigger)

    def _on_browse_text_changed(self, text):
        """Debounced entry-point: restarts the search + suggest timers."""
        # Show / hide suggestions strip
        has_text = len(text.strip()) >= 2
        if not text.strip():
            self.browse_suggest_lbl.setText("")
            self._clear_suggest_pills()
        self.browse_status.setText("Searching..." if has_text else "Type to search — random picks below")
        self.browse_progress.setVisible(has_text)
        if has_text:
            self.browse_progress.setRange(0,0)  # indeterminate
        # Restart debounce timers (caller-side debounce, NOT inside the QThread)
        self._browse_debounce.start()
        self._browse_suggest_debounce.start()

    def _on_browse_return(self):
        """Enter key: fire search immediately (skip debounce)."""
        self._browse_debounce.stop()
        self._fire_browse_search()

    def _on_browse_country_changed(self):
        """v16.7: when the country changes, re-fire the search with the new
        storefront. If the search field is empty or contains a seed query from
        a DIFFERENT country, replace it with a country-appropriate seed so the
        user sees relevant content immediately."""
        code = self.browse_country.currentData() or "US"
        self.cfg["browse_country"] = code; save_cfg(self.cfg)
        current_text = self.browse_search.text().strip()
        # v16.7: check if the current search is a seed query from a different country
        # If so, replace it with a seed from the new country
        is_seed = False
        for country_code, seeds in BROWSE_SEED_QUERIES.items():
            if current_text in seeds:
                is_seed = True; break
        if not current_text or is_seed:
            # Load a country-appropriate seed
            import random
            seeds = BROWSE_SEED_QUERIES.get(code, BROWSE_SEED_QUERIES_DEFAULT)
            new_seed = random.choice(seeds)
            self.browse_search.setText(new_seed)
            self._browse_initial_loaded = True  # prevent re-seeding
            self._browse_debounce.stop()
            self._fire_browse_search()
            print(f"[Aurora][Browse] Country changed to {code} — seed query: {new_seed!r}", flush=True)
        else:
            # User has a custom search — re-fire it with the new country
            self._browse_debounce.stop()
            self._fire_browse_search()
            print(f"[Aurora][Browse] Country changed to {code} — re-firing: {current_text!r}", flush=True)

    def _fire_browse_search(self):
        """Fire iTunes search in background (called by debounce timer or Enter).
        v16.5: fetches ALL results (up to BROWSE_MAX_TOTAL_RESULTS=200) in one
        shot. The render layer then paginates them 50 at a time as the user
        scrolls (see _fire_browse_load_more)."""
        q = self.browse_search.text().strip()
        if not q:
            self._browse_all_results = []
            self._browse_results = []
            self._browse_has_more = False
            self._render_browse_results([], is_first_page=True)
            self.browse_status.setText("Type to search — random picks below")
            self.browse_progress.setVisible(False)
            return
        self._browse_request_id += 1  # race guard
        self.browse_status.setText(f"Searching iTunes for \"{q}\"...")
        self.browse_progress.setVisible(True); self.browse_progress.setRange(0,0)
        country = self.browse_country.currentData() or "US"
        # v16.5: reset infinite-scroll state for the new query
        self._browse_last_query = q
        self._browse_last_country = country
        self._browse_has_more = False
        self._browse_loading_more = False
        self._browse_all_results = []  # full buffer of fetched tracks
        # v16.7: if the fetcher is busy (e.g. seed query still running), queue
        # this search as pending. When the fetcher finishes, _on_browse_results
        # will check for a pending search and fire it. This fixes the "search
        # doesn't work, shows random stuff" bug — previously the user's search
        # was silently dropped if the seed query's fetcher was still running.
        if self._browse_fetcher.isRunning():
            self._browse_pending_search = (q, country)
            print(f"[Aurora][Browse] Fetcher busy — queued search: {q!r} ({country})", flush=True)
        else:
            self._browse_pending_search = None
            self._browse_fetcher.search(q, country, offset=0)

    def _fire_browse_load_more(self):
        """v16.5: render the NEXT PAGE of BROWSE_RESULT_LIMIT (50) tracks from
        the already-fetched buffer (self._browse_all_results). Called by the
        scroll-area's scroll-position detector when the user scrolls near the
        bottom. NO network call is made — we already fetched everything in
        _fire_browse_search."""
        # Guard: don't fire if we're already loading more, or if there's nothing
        # more to render from the buffer.
        if self._browse_loading_more: return
        if not hasattr(self, "_browse_all_results") or not self._browse_all_results: return
        rendered = len(self._browse_results)
        total = len(self._browse_all_results)
        if rendered >= total: return
        # Show the "loading more" footer briefly (purely cosmetic — no async)
        self._browse_loading_more = True
        self._show_loading_more_footer(True)
        # Compute the next slice (BROWSE_RESULT_LIMIT more tracks)
        next_slice = self._browse_all_results[rendered:rendered + BROWSE_RESULT_LIMIT]
        # Render them (append, not replace)
        self._render_browse_results(next_slice, is_first_page=False)
        # Update has_more + footer
        self._browse_loading_more = False
        self._show_loading_more_footer(False)
        new_rendered = len(self._browse_results)
        if new_rendered < total:
            self._browse_has_more = True
            more_text = f" — scroll for more ({total - new_rendered} remaining)"
            self.browse_status.setText(f"{new_rendered} of {total} results loaded{more_text}")
        else:
            self._browse_has_more = False
            self._show_end_of_results_footer()
            self.browse_status.setText(f"{new_rendered} of {total} results — end of results")

    def _on_browse_scroll(self, value):
        """v16.5: scroll-position detector — when the user scrolls within
        BROWSE_INFINITE_SCROLL_THRESHOLD px of the bottom, fire _fire_browse_load_more().
        This is the heart of the infinite-scroll feature."""
        if not hasattr(self, "browse_scroll"): return
        sb = self.browse_scroll.verticalScrollBar()
        # value is the current scroll position (top of the viewport in px)
        # max is the maximum scroll position
        # If we're within BROWSE_INFINITE_SCROLL_THRESHOLD of the max, fire
        if sb.maximum() - value < BROWSE_INFINITE_SCROLL_THRESHOLD:
            self._fire_browse_load_more()

    def _fire_browse_suggest(self):
        """Fire iTunes suggest in background (called by debounce timer)."""
        q = self.browse_search.text().strip()
        if len(q) < 2:
            self._clear_suggest_pills()
            self.browse_suggest_lbl.setText("")
            return
        self._browse_suggest_id += 1
        country = self.browse_country.currentData() or "US"
        if not self._suggest_fetcher.isRunning():
            self._suggest_fetcher.suggest(q, country)

    def _on_browse_results(self, tracks, is_first_page, has_more):
        """v16.5: Callback from BrowseFetcher. Race-guarded.
        The fetcher returns ALL tracks (up to 200) in one shot; we render only
        the first BROWSE_RESULT_LIMIT (50) and buffer the rest for infinite
        scroll via _fire_browse_load_more().

        v16.7: After processing results, check if there's a PENDING search
        (queued because the fetcher was busy). If so, fire it now."""
        # v16.7: Check if this response is stale (a newer search was queued
        # while this one was running). If so, discard these results and fire
        # the pending search instead.
        if self._browse_pending_search is not None:
            pending_q, pending_country = self._browse_pending_search
            self._browse_pending_search = None
            # Only discard if the pending query is DIFFERENT from the one that
            # just completed (otherwise we'd loop forever)
            current_q = self.browse_search.text().strip()
            if pending_q != current_q or pending_country != (self.browse_country.currentData() or "US"):
                print(f"[Aurora][Browse] Stale results discarded — firing pending: {pending_q!r}", flush=True)
                # Fire the pending search directly (no debounce — it was already debounced)
                self.browse_search.setText(pending_q)
                self._fire_browse_search()
                return
        # Race guard: ignore stale responses from older queries.
        self.browse_progress.setVisible(False)
        self._browse_loading_more = False
        self._show_loading_more_footer(False)
        if is_first_page:
            # New query — store the FULL result set in _browse_all_results,
            # but render only the first page (BROWSE_RESULT_LIMIT).
            self._browse_all_results = list(tracks)
            first_page = tracks[:BROWSE_RESULT_LIMIT]
            self._render_browse_results(first_page, is_first_page=True)
            q = self.browse_search.text().strip()
            n_total = len(tracks)
            n_shown = len(first_page)
            if n_total == 0:
                self.browse_status.setText(f"No results for \"{q}\" — try another term or region")
                self._browse_has_more = False
            elif n_total <= n_shown:
                self._browse_has_more = False
                self.browse_status.setText(f"{n_total} result{'s' if n_total!=1 else ''} for \"{q}\"")
            else:
                self._browse_has_more = True
                self.browse_status.setText(
                    f"{n_shown} of {n_total} results for \"{q}\" — scroll for more")

    def _on_browse_suggest(self, suggestions):
        """Callback from SuggestFetcher. Render as pill buttons."""
        self._clear_suggest_pills()
        if not suggestions:
            self.browse_suggest_lbl.setText("")
            return
        self.browse_suggest_lbl.setText("Suggestions:")
        # Add up to 8 pills to the host layout
        host_layout = self.browse_suggest_host.layout()
        # Remove the trailing stretch, add pills, then re-add stretch
        while host_layout.count():
            it = host_layout.takeAt(0)
            w = it.widget()
            if w: w.deleteLater()
        for s in suggestions[:BROWSE_SUGGEST_LIMIT]:
            pill = QPushButton(s); pill.setObjectName("suggestPill")
            pill.setCursor(Qt.PointingHandCursor)
            pill.clicked.connect(lambda _, ss=s: self._apply_suggestion(ss))
            host_layout.addWidget(pill)
        host_layout.addStretch()

    def _apply_suggestion(self, text):
        """User clicked a suggestion pill — replace the search query and fire."""
        self.browse_search.setText(text)
        self.browse_search.setFocus()
        self._browse_debounce.stop()
        self._fire_browse_search()

    def _clear_suggest_pills(self):
        if not hasattr(self, "browse_suggest_host"): return
        host_layout = self.browse_suggest_host.layout()
        if host_layout is None: return
        while host_layout.count():
            it = host_layout.takeAt(0)
            w = it.widget()
            if w: w.deleteLater()
        host_layout.addStretch()

    def _render_browse_results(self, tracks, is_first_page=True):
        """v16.5: Lay out BrowseResultCard widgets in the grid. If is_first_page
        is True (default), clear the grid first; otherwise APPEND to the existing
        grid (infinite-scroll pagination)."""
        grid = self.browse_grid
        if is_first_page:
            # Clear old cards + footer
            while grid.count():
                it = grid.takeAt(0)
                w = it.widget()
                if w: w.deleteLater()
            self._browse_results = list(tracks)
            start_idx = 0
        else:
            # Append — preserve existing cards/results
            start_idx = len(self._browse_results)
            self._browse_results.extend(tracks)
        # Determine columns based on current grid width (responsive)
        grid_width = max(400, self.browse_grid.parent().width() if self.browse_grid.parent() else 1000)
        cols = max(3, min(6, grid_width // (BrowseResultCard.CARD_W + 14)))
        for i, t in enumerate(tracks):
            card = BrowseResultCard(t, self._thumb_loader, self)
            # v16.5: no preview button — only download signal is wired
            card.downloadRequested.connect(self._browse_download)
            # v16.7: double-click on card → play (download first if needed)
            card.playRequested.connect(self._browse_play)
            r, c = divmod(start_idx + i, cols)
            grid.addWidget(card, r, c)
        if is_first_page and not tracks:
            # Empty state
            empty = QLabel("No results — try a different search term or region.")
            empty.setObjectName("browseEmpty")
            empty.setAlignment(Qt.AlignCenter)
            grid.addWidget(empty, 0, 0, 1, cols)

    def _show_loading_more_footer(self, show=True):
        """v16.5: show/hide the 'Loading more…' footer label at the bottom of the grid."""
        grid = self.browse_grid
        # Find existing footer and remove it
        for i in range(grid.count() - 1, -1, -1):
            it = grid.itemAt(i)
            w = it.widget() if it else None
            if w and hasattr(w, "_is_loading_footer"):
                grid.takeAt(i); w.deleteLater()
        if show:
            grid_width = max(400, self.browse_grid.parent().width() if self.browse_grid.parent() else 1000)
            cols = max(3, min(6, grid_width // (BrowseResultCard.CARD_W + 14)))
            footer = QLabel("\u21BB  Loading more results…")
            footer.setObjectName("browseLoadingMore")
            footer.setAlignment(Qt.AlignCenter)
            footer._is_loading_footer = True
            n_rows = (len(self._browse_results) + cols - 1) // cols
            grid.addWidget(footer, n_rows, 0, 1, cols)

    def _show_end_of_results_footer(self):
        """v16.5: show 'end of results' footer when iTunes runs out."""
        grid = self.browse_grid
        grid_width = max(400, self.browse_grid.parent().width() if self.browse_grid.parent() else 1000)
        cols = max(3, min(6, grid_width // (BrowseResultCard.CARD_W + 14)))
        footer = QLabel(f"\u2014  End of results  ({len(self._browse_results)} shown)  \u2014")
        footer.setObjectName("browseEndOfResults")
        footer.setAlignment(Qt.AlignCenter)
        footer._is_loading_footer = True
        n_rows = (len(self._browse_results) + cols - 1) // cols
        grid.addWidget(footer, n_rows, 0, 1, cols)

    def _browse_preview(self, track):
        """Play the 30-sec iTunes previewUrl through the existing QMediaPlayer.
        The preview is added to a temporary 'Browse Previews' playlist so it
        shows up in the player bar with proper title/artist."""
        if not track or not track.preview_url:
            print("[Aurora][Browse] no preview URL", flush=True); return
        # Save the real (library) playback so user can resume after preview
        print(f"[Aurora][Browse] preview: {track.title} - {track.artist}", flush=True)
        # Set as current track (synthetic song dict so play_idx / player bar work)
        synth = {
            "title": track.title, "artist": track.artist, "album": track.album or "iTunes Preview",
            "duration": track.duration_ms // 1000 if track.duration_ms else 30,
            "art": None, "path": track.preview_url, "date": 0,
            "_is_preview": True, "_track_id": track.track_id,
        }
        # Try to load artwork as QImage
        try:
            if track.artwork_url:
                # Use the QNetworkAccessManager to fetch artwork async
                url = track.artwork(300)
                def _on_art(pm):
                    if pm and not pm.isNull():
                        # Update the player bar album art + backdrop
                        try:
                            self.art.setPixmap(_rounded_pixmap(
                                pm.scaled(64,64,Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation).copy(0,0,64,64), 12))
                            self.backdrop.set_art(pm.toImage())
                        except Exception: pass
                self._thumb_loader.load(url, _on_art, size=300)
        except Exception as e:
            print(f"[Aurora][Browse] preview artwork load failed: {e}", flush=True)
        # Insert synth track at front of library temporarily and play it
        # (avoids touching play_idx which assumes library index)
        self.cur = synth
        self.cur_idx = -1
        self.tl.setText(synth["title"]); self.al.setText(synth["artist"])
        # Beat graph: use pseudo levels since this is a stream URL not a file
        self.viz.set_levels(pseudo_levels(synth["path"], synth["duration"]), False)
        # Stop + swap source + play (with fade-in)
        self.audio.setVolume(0.0)
        self.player.stop()
        self.player.setSource(QUrl(track.preview_url))
        self.player.play()
        self.playing=True; self.pp.setIcon(self._ai)
        self._fade_in()
        if hasattr(self, 'tray') and self.tray.isVisible():
            self.tray.showMessage(APP_NAME, f"Preview: {synth['title']}")

    def _browse_play(self, track):
        """v16.9: Double-click on a Browse card to play the 30-second iTunes
        preview. Does NOT download — the preview is streamed instantly via
        QMediaPlayer from iTunes' previewUrl (.m4a, 30 seconds).

        This is the correct behavior: double-click = instant preview, NOT
        download. The Download button (single click) is for full-track download.

        If the song is already downloaded (full track in ~/Downloads/), play
        the full downloaded file instead of the 30-second preview."""
        if not track or not track.title:
            print("[Aurora][Browse] play: no track title", flush=True); return
        # v16.9: If already downloaded as full MP3, play the full track
        dest = MUSIC_FOLDER / track.safe_filename("mp3")
        if dest.exists() and dest.stat().st_size > 10240:
            print(f"[Aurora][Browse] play: already downloaded — playing full track {dest.name}", flush=True)
            self.browse_status.setText(f"Playing (full track): {track.title}")
            self.play_file(str(dest))
            return
        # v16.9: Not downloaded — play 30-second iTunes preview (NO download)
        if not track.preview_url:
            self.browse_status.setText(f"No preview available for: {track.title} — use Download button")
            print(f"[Aurora][Browse] play: no preview_url for {track.title!r}", flush=True)
            return
        print(f"[Aurora][Browse] play: 30-second preview — {track.title} - {track.artist}", flush=True)
        self.browse_status.setText(f"Preview (30s): {track.title}")
        # Delegate to _browse_preview which handles the QMediaPlayer playback
        self._browse_preview(track)

    def _browse_download(self, track):
        """v16.5: One-click FULL-TRACK download via yt-dlp + ffmpeg. The track's
        iTunes metadata (title/artist/album/genre/release date + cover art at
        600x600) is embedded into the resulting MP3 via mutagen.

        Subsequent clicks while a download is in flight are queued (serialized)."""
        if not track or not track.title:
            print("[Aurora][Browse] no track title — cannot download", flush=True)
            return
        # Idempotent: skip if the file already exists in ~/Downloads/
        dest = MUSIC_FOLDER / track.safe_filename("mp3")
        if dest.exists() and dest.stat().st_size > 10240:
            self._mark_card_downloaded(track.track_id, True)
            self.browse_status.setText(f"Already downloaded: {track.title} — check Library")
            return
        # Find the card widget to show progress
        card = self._find_card(track.track_id)
        if card: card.set_downloading(True, 0)
        if self._downloader.isRunning():
            # Queue it — Downloader picks up next when current finishes
            if track.track_id not in [t.track_id for t in self._download_queue]:
                self._download_queue.append(track)
                self.browse_status.setText(
                    f"Queued: {track.title} ({len(self._download_queue)} in queue)")
            return
        # Start immediately
        self._downloading_id = track.track_id
        self.browse_progress.setVisible(True); self.browse_progress.setRange(0,100)
        self.browse_progress.setValue(0)
        self.browse_status.setText(f"Downloading full track: {track.title}...")
        self._downloader.download(track)

    def _on_browse_dl_progress(self, track_id, pct):
        """Update the card's download button + the global progress bar."""
        card = self._find_card(track_id)
        if card: card.set_downloading(True, pct)
        self.browse_progress.setVisible(True); self.browse_progress.setRange(0,100)
        self.browse_progress.setValue(pct)

    def _on_browse_dl_done(self, track_id, path, ok, error):
        """v16.6: Downloader finished (success or failure). Trigger rescan + next queue.
        The `error` field may contain "strategy:<name>" on success, indicating which
        bot-bypass strategy worked — display it so the user knows what's effective."""
        # Update the card visual state
        self._mark_card_downloaded(track_id, ok)
        self.browse_progress.setVisible(False)
        track_title = ""
        for t in self._browse_results:
            if t.track_id == track_id: track_title = t.title; break
        if ok:
            # v16.6: extract strategy name from error field ("strategy:<name>")
            strategy_note = ""
            if error and error.startswith("strategy:"):
                strat = error.split(":", 1)[1]
                strategy_note = f"  [via {strat}]"
            self.browse_status.setText(
                f"Downloaded: {track_title} \u2192 {path}{strategy_note}" +
                (" (already existed)" if error == "already-exists" else ""))
            # Trigger async rescan so the new file shows up in Library
            self.scan()
            # Tray notification
            if hasattr(self, 'tray') and self.tray.isVisible():
                self.tray.showMessage(APP_NAME, f"Downloaded: {track_title}")
            # v16.9: double-click no longer triggers download, so no auto-play
            # after download. (v16.7's auto-play-on-download was wrong — double-
            # click now plays the 30s preview instead via _browse_play.)
        else:
            # v16.6: friendly hint when all strategies fail due to bot-protection
            friendly = error
            if "bot-blocked" in error or "Sign in to confirm" in error:
                friendly = (f"All 6 bot-bypass strategies failed for {track_title}. "
                            f"Open Settings → YouTube Auth to configure cookies or browser auth.")
            self.browse_status.setText(f"Download failed: {friendly}")
        self._downloading_id = None
        # Dispatch next queued download
        if self._download_queue:
            next_t = self._download_queue.pop(0)
            self._downloading_id = next_t.track_id
            self.browse_status.setText(f"Downloading: {next_t.title}...")
            self.browse_progress.setVisible(True); self.browse_progress.setRange(0,100)
            self.browse_progress.setValue(0)
            self._downloader.download(next_t)
        else:
            self.browse_progress.setVisible(False)

    def _on_browse_strategy_used(self, track_id, strategy_name):
        """v16.6: callback when a download strategy succeeds. Logs which strategy
        worked so the user can see (e.g. 'via client-rotation') in the status bar."""
        print(f"[Aurora][v16.6] Download succeeded via strategy: {strategy_name}", flush=True)

    def _find_card(self, track_id):
        """Find a BrowseResultCard widget by track_id (linear scan of grid)."""
        grid = self.browse_grid
        for i in range(grid.count()):
            it = grid.itemAt(i)
            w = it.widget() if it else None
            if w and hasattr(w, "track") and w.track.track_id == track_id:
                return w
        return None

    def _mark_card_downloaded(self, track_id, ok=True):
        card = self._find_card(track_id)
        if card: card.set_downloaded(ok)

    def _browse_get_status(self):
        """v16.5: expose Browse state in --status JSON (for agent control).
        Includes infinite-scroll state: has_more, loading_more, last_query,
        last_country. The `results` array is capped at 50 to keep the JSON
        manageable — read all results via `results_count`."""
        return {
            "query": self.browse_search.text().strip() if hasattr(self, "browse_search") else "",
            "results_count": len(self._browse_results) if hasattr(self, "_browse_results") else 0,
            "results": [t.to_dict() for t in (self._browse_results or [])[:50]],
            "country": self.browse_country.currentData() if hasattr(self, "browse_country") else "US",
            "downloading": self._downloading_id if hasattr(self, "_downloading_id") else None,
            "queue_size": len(self._download_queue) if hasattr(self, "_download_queue") else 0,
            # v16.5: infinite-scroll state
            "has_more": self._browse_has_more if hasattr(self, "_browse_has_more") else False,
            "loading_more": self._browse_loading_more if hasattr(self, "_browse_loading_more") else False,
            "last_query": self._browse_last_query if hasattr(self, "_browse_last_query") else "",
            "last_country": self._browse_last_country if hasattr(self, "_browse_last_country") else "US",
            "max_total_results": BROWSE_MAX_TOTAL_RESULTS,
        }

    def _get_history_status(self):
        """v16.8: expose History state in --status JSON (for agent control)."""
        h = load_history()
        entries = h.get("entries", [])
        play_counts = h.get("play_counts", {})
        return {
            "entries_count": len(entries),
            "max_entries": HISTORY_MAX_ENTRIES,
            "entries": entries[:20],  # cap at 20 for JSON size
            "unique_songs_total": len(entries) + len(play_counts),
            "total_plays": sum(e.get("play_count", 0) for e in entries) + sum(play_counts.values()),
            "evicted_play_counts": play_counts,
        }

    def _get_session_status(self):
        """v16.8: expose session time stats in --status JSON."""
        try:
            sess = load_session()
            started = datetime.fromisoformat(sess.get("session_started", datetime.now().isoformat()))
            session_seconds = (datetime.now() - started).total_seconds()
            total_seconds = sess.get("total_app_seconds", 0) + session_seconds
            return {
                "session_started": sess.get("session_started", ""),
                "session_seconds": int(session_seconds),
                "session_human": fmt_duration(session_seconds),
                "total_app_seconds": int(total_seconds),
                "total_app_human": fmt_duration(total_seconds),
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_equalizer_status(self):
        """v17.0: expose EQ state in --status JSON."""
        eq = load_equalizer()
        return {
            "enabled": eq.get("enabled", False),
            "preset": eq.get("preset", "Flat"),
            "gains": eq.get("gains", [0]*EQ_BANDS_COUNT),
            "bands_hz": EQ_BANDS_HZ,
            "bands_count": EQ_BANDS_COUNT,
        }

    def _get_repeat_stats_status(self):
        """v17.0: expose repeat/skip stats in --status JSON."""
        rs = load_repeat_stats()
        # Get repeat count for current song
        current_repeat = 0
        if self.cur:
            path = self.cur.get("path", "")
            title = self.cur.get("title", "")
            current_repeat = get_song_repeat_count(path, title)
        return {
            "skip_forward_count": rs.get("skip_forward_count", 0),
            "skip_backward_count": rs.get("skip_backward_count", 0),
            "current_song_repeat_count": current_repeat,
            "total_unique_repeated_songs": len(rs.get("song_repeats", {})),
            "total_repeats": sum(rs.get("song_repeats", {}).values()),
        }

    # ====================================================================
    # v16.8 — HISTORY VIEW (last 100 played songs + session stats)
    # ====================================================================
    def _history_view(self):
        """v16.8: History page — shows the last 100 played songs with:
        - title, artist
        - date + exact time of last play
        - play count (how many times this song was played)
        - first-played date
        Plus a stats panel at the top:
        - Current session time (time since app opened)
        - Total cumulative time (across all sessions)
        - Total unique songs played
        - Total play count (sum of all play_count fields)
        """
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        t=QLabel("History"); t.setObjectName("pageTitle"); l.addWidget(t)
        self.history_sub=QLabel("Last 100 played songs — double-click to replay")
        self.history_sub.setObjectName("pageSubtitle"); l.addWidget(self.history_sub)

        # --- Stats panel (4 cards in a row) ---
        stats_row = QHBoxLayout(); stats_row.setContentsMargins(28,4,28,12); stats_row.setSpacing(12)
        def stat_card(icon, label, value, color_key="primary"):
            c = QFrame(); c.setObjectName("settingsCard")
            cl = QVBoxLayout(c); cl.setContentsMargins(16,12,16,14); cl.setSpacing(4)
            h = QHBoxLayout(); h.setSpacing(8)
            ic = QLabel(); ic.setPixmap(_svg(icon, M3[color_key]).pixmap(20,20)); ic.setFixedSize(22,22)
            h.addWidget(ic)
            lbl = QLabel(label); lbl.setObjectName("cardDesc"); h.addWidget(lbl); h.addStretch()
            cl.addLayout(h)
            val = QLabel(value); val.setObjectName("cardTitle")
            val.setStyleSheet(f"font-size:18px; font-weight:600; color:{M3['on_surface']};")
            cl.addWidget(val)
            return c
        self._hist_stat_session = stat_card(IC_TIMER, "This session", "0s")
        self._hist_stat_total = stat_card(IC_TIMER, "Total time", "0s")
        self._hist_stat_songs = stat_card(IC_HISTORY, "Unique songs", "0")
        self._hist_stat_plays = stat_card(IC_REPEAT_COUNT, "Total plays", "0")
        stats_row.addWidget(self._hist_stat_session)
        stats_row.addWidget(self._hist_stat_total)
        stats_row.addWidget(self._hist_stat_songs)
        stats_row.addWidget(self._hist_stat_plays)
        l.addLayout(stats_row)

        # v17.2: Current Song Stats panel — shows date/time, repeat count, skip
        # fwd/bwd for the currently playing song. Uses SVG icons (NO emojis).
        # This is the panel that USED to be in the player bar (v17.0/v17.1) —
        # now moved to History page per user request.
        cur_stats_card = QFrame(); cur_stats_card.setObjectName("settingsCard")
        csc_layout = QVBoxLayout(cur_stats_card); csc_layout.setContentsMargins(16,12,16,14); csc_layout.setSpacing(8)
        csc_title = QLabel("Current Song Stats"); csc_title.setObjectName("cardTitle")
        csc_layout.addWidget(csc_title)
        csc_row = QHBoxLayout(); csc_row.setSpacing(16); csc_row.setContentsMargins(0,0,0,0)
        # Helper: create an icon+text stat pair
        def _hist_stat_pair(icon_path, text, name):
            pair = QWidget(); pair.setObjectName(f"hist_stat_{name}")
            pl = QHBoxLayout(pair); pl.setContentsMargins(0,0,0,0); pl.setSpacing(4)
            icon_lbl = QLabel(); icon_lbl.setPixmap(_svg(icon_path, M3["primary"]).pixmap(16,16))
            icon_lbl.setFixedSize(18,18); pl.addWidget(icon_lbl)
            txt_lbl = QLabel(text); txt_lbl.setObjectName("cardDesc")
            pl.addWidget(txt_lbl)
            return pair, txt_lbl, icon_lbl
        self._hist_cur_date_pair, self._hist_cur_date_text, self._hist_cur_date_icon = _hist_stat_pair(IC_CALENDAR, "—", "date")
        self._hist_cur_repeat_pair, self._hist_cur_repeat_text, self._hist_cur_repeat_icon = _hist_stat_pair(IC_REPEAT_COUNT_ICON, "0x", "repeat")
        self._hist_cur_skipfwd_pair, self._hist_cur_skipfwd_text, self._hist_cur_skipfwd_icon = _hist_stat_pair(IC_SKIP_FWD, "0x", "skipfwd")
        self._hist_cur_skipbwd_pair, self._hist_cur_skipbwd_text, self._hist_cur_skipbwd_icon = _hist_stat_pair(IC_SKIP_BWD, "0x", "skipbwd")
        csc_row.addWidget(self._hist_cur_date_pair)
        csc_row.addWidget(self._hist_cur_repeat_pair)
        csc_row.addWidget(self._hist_cur_skipfwd_pair)
        csc_row.addWidget(self._hist_cur_skipbwd_pair)
        csc_row.addStretch()
        csc_layout.addLayout(csc_row)
        l.addWidget(cur_stats_card)
        # Add margins around the card
        cur_stats_card.setStyleSheet(f"margin: 0 28px;")

        # --- Clear button row ---
        clr_row = QHBoxLayout(); clr_row.setContentsMargins(28,0,28,12); clr_row.setSpacing(8)
        clr_btn = QPushButton("  Clear History"); clr_btn.setObjectName("dangerBtn")
        clr_btn.setIcon(_svg(IC_TRASH, M3["error"])); clr_btn.setCursor(Qt.PointingHandCursor)
        clr_btn.clicked.connect(self._clear_history)
        clr_row.addWidget(clr_btn)
        clr_row.addStretch()
        l.addLayout(clr_row)

        # --- History list ---
        self.history_list = QListWidget(); self.history_list.setObjectName("songList")
        self.history_list.itemDoubleClicked.connect(self._history_play)
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._history_ctx)
        # Use the same rich delegate as Library for consistency
        self.history_delegate = TrackDelegate(self,
            rows=lambda: self._history_song_dicts(),
            current=lambda: -1)
        self.history_list.setItemDelegate(self.history_delegate)
        self.history_list.setMouseTracking(True); self.history_list.setUniformItemSizes(True)
        l.addWidget(self.history_list)

        # State
        self._history_entries = []  # list of dicts (from load_history)
        return w

    def _history_song_dicts(self):
        """Convert history entries into the song-dict shape TrackDelegate expects."""
        out = []
        for e in self._history_entries:
            out.append({
                "title": e.get("title", ""),
                "artist": e.get("artist", ""),
                "album": "",
                "duration": 0,
                "art": None,
                "path": e.get("path", ""),
                "date": 0,
            })
        return out

    def _refresh_history(self):
        """v16.8: Reload history from disk + refresh the list widget + stats."""
        h = load_history()
        self._history_entries = h.get("entries", [])
        # Populate list
        self.history_list.clear()
        for i, e in enumerate(self._history_entries):
            title = e.get("title", "")
            artist = e.get("artist", "")
            play_count = e.get("play_count", 1)
            last_played = e.get("last_played", "")
            # Format: "  Title  -  Artist  •  played Nx  •  YYYY-MM-DD HH:MM"
            try:
                dt = datetime.fromisoformat(last_played) if last_played else None
                date_str = dt.strftime("%Y-%m-%d %H:%M") if dt else ""
            except Exception:
                date_str = last_played[:16] if last_played else ""
            count_str = f"played {play_count}x" if play_count > 1 else "played once"
            txt = f"  {title}  -  {artist}  •  {count_str}  •  {date_str}"
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(txt)
            item.setData(Qt.UserRole, i)
            self.history_list.addItem(item)
        # Update stats
        self._update_history_stats(h)
        # v17.2: Update the Current Song Stats panel with SVG icons
        self._update_current_song_stats()
        # Update subtitle
        n = len(self._history_entries)
        if hasattr(self, "history_sub"):
            self.history_sub.setText(
                f"{n} of {HISTORY_MAX_ENTRIES} songs — double-click to replay" if n else
                "No history yet — play a song to start tracking")

    def _update_history_stats(self, h=None):
        """v16.8: Refresh the 4 stat cards (session time, total time, unique songs, total plays)."""
        if h is None: h = load_history()
        # Session time: time since session_started
        try:
            sess = load_session()
            started = datetime.fromisoformat(sess.get("session_started", datetime.now().isoformat()))
            session_seconds = (datetime.now() - started).total_seconds()
        except Exception:
            session_seconds = 0
        total_seconds = sess.get("total_app_seconds", 0) + session_seconds
        # Unique songs = len(entries) + len(play_counts for evicted)
        entries = h.get("entries", [])
        play_counts = h.get("play_counts", {})
        unique_songs = len(entries) + len(play_counts)
        # Total plays = sum of play_count in entries + sum of play_counts
        total_plays = sum(e.get("play_count", 0) for e in entries) + sum(play_counts.values())
        # Update labels
        if hasattr(self, "_hist_stat_session"):
            # Find the value QLabel (second child of the card's layout)
            for card, value in [
                (self._hist_stat_session, fmt_duration(session_seconds)),
                (self._hist_stat_total, fmt_duration(total_seconds)),
                (self._hist_stat_songs, str(unique_songs)),
                (self._hist_stat_plays, str(total_plays)),
            ]:
                # The value label is the 2nd widget in the card's QVBoxLayout
                cl = card.layout()
                if cl and cl.count() >= 2:
                    item = cl.itemAt(1)
                    if item and item.widget():
                        item.widget().setText(value)
        # Schedule a periodic refresh so session time ticks up while the page is open
        if not hasattr(self, "_history_stats_timer"):
            self._history_stats_timer = QTimer(self)
            self._history_stats_timer.setInterval(1000)  # 1 second
            self._history_stats_timer.timeout.connect(lambda: (self._update_history_stats(), self._update_current_song_stats()))
            self._history_stats_timer.start()

    def _update_current_song_stats(self):
        """v17.2: Update the Current Song Stats panel inside the History page.
        Shows date/time, repeat count, skip fwd/bwd for the currently playing
        song — using SVG icons (NO emojis). This panel was moved from the
        player bar (v17.0/v17.1) to the History page per user request."""
        if not hasattr(self, "_hist_cur_date_text"): return
        if not self.cur:
            self._hist_cur_date_text.setText("No song playing")
            self._hist_cur_repeat_text.setText("0x")
            self._hist_cur_skipfwd_text.setText("0x")
            self._hist_cur_skipbwd_text.setText("0x")
            return
        path = self.cur.get("path", "")
        title = self.cur.get("title", "")
        # Get repeat count for this song
        repeat_count = get_song_repeat_count(path, title)
        # Get current date/time from laptop
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d %H:%M")
        # Get skip stats
        rs = load_repeat_stats()
        skip_fwd = rs.get("skip_forward_count", 0)
        skip_bwd = rs.get("skip_backward_count", 0)
        # Update text labels
        self._hist_cur_date_text.setText(date_str)
        self._hist_cur_repeat_text.setText(f"{repeat_count}x")
        self._hist_cur_skipfwd_text.setText(f"{skip_fwd}x")
        self._hist_cur_skipbwd_text.setText(f"{skip_bwd}x")
        # Re-tint icons with current M3 palette
        self._hist_cur_date_icon.setPixmap(_svg(IC_CALENDAR, M3["primary"]).pixmap(16,16))
        self._hist_cur_repeat_icon.setPixmap(_svg(IC_REPEAT_COUNT_ICON, M3["primary"]).pixmap(16,16))
        self._hist_cur_skipfwd_icon.setPixmap(_svg(IC_SKIP_FWD, M3["primary"]).pixmap(16,16))
        self._hist_cur_skipbwd_icon.setPixmap(_svg(IC_SKIP_BWD, M3["primary"]).pixmap(16,16))

    def _history_play(self, item):
        """v16.8: double-click on a history entry → play it (if file still exists)."""
        idx = item.data(Qt.UserRole)
        if idx < 0 or idx >= len(self._history_entries): return
        e = self._history_entries[idx]
        path = e.get("path", "")
        title = e.get("title", "")
        if path and Path(path).exists():
            self.play_file(path)
        else:
            # File gone — try to find by title in library
            for s in self.songs:
                if s.get("title", "").lower() == title.lower():
                    self.play_idx(self.songs.index(s)); return
            print(f"[Aurora][History] file not found: {path}", flush=True)
            if hasattr(self, "history_sub"):
                self.history_sub.setText(f"File not found: {title} — may have been deleted")

    def _history_ctx(self, pos):
        """v16.8: right-click context menu on history entries."""
        from PySide6.QtGui import QAction
        item = self.history_list.itemAt(pos)
        if not item: return
        idx = item.data(Qt.UserRole)
        if idx < 0 or idx >= len(self._history_entries): return
        e = self._history_entries[idx]
        m = QMenu()
        a_play = QAction("Play", self); a_play.triggered.connect(lambda: self._history_play(item))
        m.addAction(a_play)
        a_info = QAction("Show details", self)
        a_info.triggered.connect(lambda: self._show_history_info(idx))
        m.addAction(a_info)
        a_remove = QAction("Remove from history", self)
        a_remove.triggered.connect(lambda: self._remove_history_entry(idx))
        m.addAction(a_remove)
        m.exec(self.history_list.mapToGlobal(pos))

    def _show_history_info(self, idx):
        """v16.8: show a dialog with full metadata for a history entry."""
        from PySide6.QtWidgets import QMessageBox
        if idx < 0 or idx >= len(self._history_entries): return
        e = self._history_entries[idx]
        title = e.get("title", "")
        artist = e.get("artist", "")
        path = e.get("path", "")
        play_count = e.get("play_count", 1)
        first = e.get("first_played", "")
        last = e.get("last_played", "")
        try:
            first_dt = datetime.fromisoformat(first) if first else None
            last_dt = datetime.fromisoformat(last) if last else None
            first_str = first_dt.strftime("%Y-%m-%d %H:%M:%S") if first_dt else "—"
            last_str = last_dt.strftime("%Y-%m-%d %H:%M:%S") if last_dt else "—"
        except Exception:
            first_str = first; last_str = last
        info = (f"Title: {title}\n\n"
                f"Artist: {artist}\n\n"
                f"Play count: {play_count}\n\n"
                f"First played: {first_str}\n\n"
                f"Last played: {last_str}\n\n"
                f"File path: {path}")
        QMessageBox.information(self, "History Details", info)

    def _remove_history_entry(self, idx):
        """v16.8: remove a single entry from history."""
        if idx < 0 or idx >= len(self._history_entries): return
        h = load_history()
        if 0 <= idx < len(h.get("entries", [])):
            h["entries"].pop(idx)
            save_history(h)
            self._refresh_history()

    def _clear_history(self):
        """v16.8: clear all history entries (with confirmation)."""
        from PySide6.QtWidgets import QMessageBox
        ret = QMessageBox.question(self, "Clear History",
            "Clear all 100 history entries? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.Yes:
            h = load_history()
            h["entries"] = []
            # Keep play_counts + total_app_seconds (those are cumulative stats)
            save_history(h)
            self._refresh_history()
            print("[Aurora][History] cleared", flush=True)

    # ====================================================================
    # v17.0 — EQUALIZER VIEW (10-band + presets + animated visualizer)
    # ====================================================================
    def _equalizer_view(self):
        """v17.0: Equalizer page — 10-band animated frequency visualizer with:
        - Enable/disable toggle
        - 10 vertical bars (31Hz to 16kHz), click to adjust gain (-12 to +12 dB)
        - Preset dropdown (Flat, Bass Boost, Treble Boost, Vocal, Rock, Pop, Jazz, ...)
        - Reset to Flat button
        - Live animation when audio is playing (motion graphics)
        NOTE: The EQ gains are visualized but actual audio DSP requires
        QAudioProbe + a real-time filter chain. For now, the gains are
        stored and the visualizer animates — full DSP is a future enhancement."""
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        t=QLabel("Equalizer"); t.setObjectName("pageTitle"); l.addWidget(t)
        self.eq_sub=QLabel("10-band equalizer — click bars to adjust gain")
        self.eq_sub.setObjectName("pageSubtitle"); l.addWidget(self.eq_sub)
        # --- Toolbar: enable toggle + preset dropdown + reset ---
        bar=QHBoxLayout(); bar.setContentsMargins(28,0,28,12); bar.setSpacing(10)
        # Enable toggle
        eq_cfg = load_equalizer()
        self.eq_enable_btn = QPushButton("  EQ: ON" if eq_cfg.get("enabled") else "  EQ: OFF")
        self.eq_enable_btn.setObjectName("tonalBtn"); self.eq_enable_btn.setCheckable(True)
        self.eq_enable_btn.setChecked(eq_cfg.get("enabled", False))
        self.eq_enable_btn.setIcon(_svg(IC_CHECK, M3["on_secondary_container"]))
        self.eq_enable_btn.setCursor(Qt.PointingHandCursor)
        self.eq_enable_btn.clicked.connect(self._on_eq_toggle)
        bar.addWidget(self.eq_enable_btn)
        # Preset dropdown
        pl = QLabel("Preset:"); pl.setObjectName("cardDesc"); bar.addWidget(pl)
        self.eq_preset_combo = QComboBox(); self.eq_preset_combo.setObjectName("sortCombo")
        for name in EQ_PRESETS:
            self.eq_preset_combo.addItem(name)
        # Set current preset
        saved_preset = eq_cfg.get("preset", "Flat")
        idx = self.eq_preset_combo.findText(saved_preset)
        if idx >= 0: self.eq_preset_combo.setCurrentIndex(idx)
        self.eq_preset_combo.currentIndexChanged.connect(self._on_eq_preset_changed)
        bar.addWidget(self.eq_preset_combo)
        # Reset button
        rb = QPushButton("  Reset to Flat"); rb.setObjectName("tonalBtn")
        rb.setIcon(_svg(IC_REFRESH, M3["on_secondary_container"]))
        rb.setCursor(Qt.PointingHandCursor)
        rb.clicked.connect(lambda: self._apply_eq_preset("Flat"))
        bar.addWidget(rb)
        bar.addStretch()
        l.addLayout(bar)
        # --- Equalizer widget (the animated 10-band visualizer) ---
        self.eq_widget = EqualizerWidget(self)
        self.eq_widget.win = self
        self.eq_widget.set_gains(eq_cfg.get("gains", [0]*EQ_BANDS_COUNT))
        l.addWidget(self.eq_widget, stretch=1)
        # --- Info card explaining the bands ---
        info = QLabel(
            "Bands: 31Hz (sub-bass) · 62Hz (bass) · 125Hz (upper bass) · 250Hz (low mids) · "
            "500Hz (mids) · 1kHz (upper mids) · 2kHz (presence) · 4kHz (high mids) · "
            "8kHz (treble) · 16kHz (air)\n\n"
            "Click a bar to set its gain. Positive gain (primary color) = boost, "
            "negative gain (error color) = cut. The visualizer animates with the beat "
            "when audio is playing."
        )
        info.setObjectName("cardDesc"); info.setWordWrap(True)
        info.setStyleSheet(f"padding:16px 28px; background:rgba(27,27,33,0.5); border-radius:12px; margin:0 28px 24px;")
        l.addWidget(info)
        return w

    def _refresh_equalizer(self):
        """v17.0: Refresh the EQ page from disk (called on page switch)."""
        eq_cfg = load_equalizer()
        if hasattr(self, "eq_widget"):
            self.eq_widget.set_gains(eq_cfg.get("gains", [0]*EQ_BANDS_COUNT))
        if hasattr(self, "eq_enable_btn"):
            self.eq_enable_btn.setChecked(eq_cfg.get("enabled", False))
            self.eq_enable_btn.setText("  EQ: ON" if eq_cfg.get("enabled") else "  EQ: OFF")
        if hasattr(self, "eq_preset_combo"):
            idx = self.eq_preset_combo.findText(eq_cfg.get("preset", "Flat"))
            if idx >= 0: self.eq_preset_combo.setCurrentIndex(idx)

    def _on_eq_toggle(self):
        """v17.0: Enable/disable the equalizer."""
        eq_cfg = load_equalizer()
        eq_cfg["enabled"] = self.eq_enable_btn.isChecked()
        save_equalizer(eq_cfg)
        self.eq_enable_btn.setText("  EQ: ON" if eq_cfg["enabled"] else "  EQ: OFF")
        print(f"[Aurora][EQ] enabled={eq_cfg['enabled']}", flush=True)

    def _on_eq_preset_changed(self):
        """v17.0: Apply the selected preset."""
        preset_name = self.eq_preset_combo.currentText()
        self._apply_eq_preset(preset_name)

    def _apply_eq_preset(self, preset_name):
        """v17.0: Apply a named preset to the EQ."""
        if preset_name not in EQ_PRESETS:
            print(f"[Aurora][EQ] unknown preset: {preset_name}", flush=True); return
        gains = list(EQ_PRESETS[preset_name])
        eq_cfg = load_equalizer()
        eq_cfg["gains"] = gains
        eq_cfg["preset"] = preset_name
        save_equalizer(eq_cfg)
        if hasattr(self, "eq_widget"):
            self.eq_widget.set_gains(gains)
        # Update the preset combo
        if hasattr(self, "eq_preset_combo"):
            idx = self.eq_preset_combo.findText(preset_name)
            if idx >= 0: self.eq_preset_combo.setCurrentIndex(idx)
        print(f"[Aurora][EQ] preset={preset_name} gains={gains}", flush=True)

    def _on_eq_band_changed(self, band, gain):
        """v17.0: Called when the user clicks/drags a band in the EqualizerWidget."""
        eq_cfg = load_equalizer()
        if band < 0 or band >= EQ_BANDS_COUNT: return
        eq_cfg["gains"][band] = gain
        eq_cfg["preset"] = "Custom"  # no longer matches a built-in preset
        save_equalizer(eq_cfg)
        # Update the preset combo to "Custom" (add it if not present)
        if hasattr(self, "eq_preset_combo"):
            if self.eq_preset_combo.findText("Custom") < 0:
                self.eq_preset_combo.addItem("Custom")
            self.eq_preset_combo.setCurrentText("Custom")

    def _on_eq_changed(self, gains):
        """v17.0: Called when the user releases the mouse on the EqualizerWidget.
        Saves the full 10-band gain set."""
        eq_cfg = load_equalizer()
        eq_cfg["gains"] = list(gains)[:EQ_BANDS_COUNT]
        save_equalizer(eq_cfg)

    # ===== v15: Playlists — overview grid + detail page (finally functional) ==
    def _pl_view(self):
        self.plstack=QStackedWidget()
        # --- page 0: overview ---
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        t=QLabel("Playlists"); t.setObjectName("pageTitle"); l.addWidget(t)
        s=QLabel("Double-click a playlist to open it"); s.setObjectName("pageSubtitle"); l.addWidget(s)
        bl=QHBoxLayout(); bl.setContentsMargins(28,0,28,12)
        cb=QPushButton("  New Playlist"); cb.setObjectName("createBtn"); cb.setIcon(_svg(IC_PLUS,M3["on_primary"])); cb.setCursor(Qt.PointingHandCursor); cb.clicked.connect(self._newpl); bl.addWidget(cb)
        self._newpl_btn=cb
        bl.addStretch(); l.addLayout(bl)
        self.pllist=QListWidget(); self.pllist.setObjectName("playlistList")
        self.pllist.itemDoubleClicked.connect(lambda it: self._open_pl(it.data(Qt.UserRole)))
        self.pllist.setContextMenuPolicy(Qt.CustomContextMenu); self.pllist.customContextMenuRequested.connect(self._pl_ctx)
        l.addWidget(self.pllist)
        self.plstack.addWidget(w)
        # --- page 1: detail ---
        d=QWidget(); dl=QVBoxLayout(d); dl.setContentsMargins(0,0,0,0); dl.setSpacing(0)
        hd=QHBoxLayout(); hd.setContentsMargins(24,20,28,4); hd.setSpacing(12)
        bb=QPushButton(""); bb.setIcon(_svg(IC_BACK)); bb.setObjectName("controlButton"); bb.setFixedSize(40,40); bb.setToolTip("Back to playlists"); bb.setCursor(Qt.PointingHandCursor)
        bb.clicked.connect(lambda: (self.plstack.setCurrentIndex(0), self._refpl())); hd.addWidget(bb)
        self._pl_back_btn=bb
        tv=QVBoxLayout(); tv.setSpacing(2)
        self.pl_title=QLabel("Playlist"); self.pl_title.setObjectName("plDetailTitle"); tv.addWidget(self.pl_title)
        self.pl_sub=QLabel(""); self.pl_sub.setObjectName("plDetailSub"); tv.addWidget(self.pl_sub)
        hd.addLayout(tv,stretch=1); dl.addLayout(hd)
        ab=QHBoxLayout(); ab.setContentsMargins(28,10,28,12); ab.setSpacing(8)
        pb2=QPushButton("  Play"); pb2.setObjectName("createBtn"); pb2.setIcon(_svg(IC_PLAY,M3["on_primary"])); pb2.setCursor(Qt.PointingHandCursor); pb2.clicked.connect(lambda: self.play_playlist(self._pl_open)); ab.addWidget(pb2)
        self._pl_play_btn=pb2
        adb=QPushButton("  Add Songs"); adb.setObjectName("tonalBtn"); adb.setIcon(_svg(IC_PLAYLIST_ADD,M3["on_secondary_container"])); adb.setCursor(Qt.PointingHandCursor); adb.clicked.connect(self._pl_add_songs); ab.addWidget(adb)
        self._pl_add_btn=adb
        rnb=QPushButton("  Rename"); rnb.setObjectName("tonalBtn"); rnb.setIcon(_svg(IC_EDIT,M3["on_secondary_container"])); rnb.setCursor(Qt.PointingHandCursor); rnb.clicked.connect(self._pl_rename); ab.addWidget(rnb)
        self._pl_ren_btn=rnb
        deb=QPushButton("  Delete"); deb.setObjectName("dangerBtn"); deb.setIcon(_svg(IC_TRASH,M3["error"])); deb.setCursor(Qt.PointingHandCursor); deb.clicked.connect(self._pl_delete); ab.addWidget(deb)
        self._pl_del_btn=deb
        ab.addStretch(); dl.addLayout(ab)
        self.pl_songlist=QListWidget(); self.pl_songlist.setObjectName("songList")
        self.pl_delegate=TrackDelegate(self, rows=lambda: self._pl_songs,
            current=lambda: next((i for i,s in enumerate(self._pl_songs) if self.cur and s["path"]==self.cur["path"]), -1))
        self.pl_songlist.setItemDelegate(self.pl_delegate)
        self.pl_songlist.setMouseTracking(True); self.pl_songlist.setUniformItemSizes(True)
        self.pl_songlist.itemDoubleClicked.connect(lambda it: self.play_playlist(self._pl_open, it.data(Qt.UserRole)))
        self.pl_songlist.setContextMenuPolicy(Qt.CustomContextMenu); self.pl_songlist.customContextMenuRequested.connect(self._pl_song_ctx)
        dl.addWidget(self.pl_songlist)
        self.plstack.addWidget(d)
        self._pl_open=None; self._pl_songs=[]
        return self.plstack

    # ===== v15: Queue page — remove / reorder / clear / save (finally usable) =
    def _q_view(self):
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(0)
        t=QLabel("Queue"); t.setObjectName("pageTitle"); l.addWidget(t)
        self.q_sub=QLabel("Up next — double-click to jump, right-click or Delete key to remove"); self.q_sub.setObjectName("pageSubtitle"); l.addWidget(self.q_sub)
        tb=QHBoxLayout(); tb.setContentsMargins(28,0,28,12); tb.setSpacing(8)
        ub=QPushButton(""); ub.setIcon(_svg(IC_UP)); ub.setObjectName("controlButton"); ub.setFixedSize(40,40); ub.setToolTip("Move up"); ub.setCursor(Qt.PointingHandCursor); ub.clicked.connect(lambda: self._q_move(-1)); tb.addWidget(ub)
        db=QPushButton(""); db.setIcon(_svg(IC_DOWN)); db.setObjectName("controlButton"); db.setFixedSize(40,40); db.setToolTip("Move down"); db.setCursor(Qt.PointingHandCursor); db.clicked.connect(lambda: self._q_move(1)); tb.addWidget(db)
        rb=QPushButton(""); rb.setIcon(_svg(IC_CLOSE)); rb.setObjectName("controlButton"); rb.setFixedSize(40,40); rb.setToolTip("Remove selected (Del)"); rb.setCursor(Qt.PointingHandCursor); rb.clicked.connect(self._q_remove_sel); tb.addWidget(rb)
        self._q_btns=[ub,db,rb]
        tb.addStretch()
        sv=QPushButton("  Save as Playlist"); sv.setObjectName("tonalBtn"); sv.setIcon(_svg(IC_PLAYLIST_ADD,M3["on_secondary_container"])); sv.setCursor(Qt.PointingHandCursor); sv.clicked.connect(self._q_save_pl); tb.addWidget(sv)
        self._q_save_btn=sv
        cb=QPushButton("  Clear Queue"); cb.setObjectName("dangerBtn"); cb.setIcon(_svg(IC_TRASH,M3["error"])); cb.setCursor(Qt.PointingHandCursor); cb.clicked.connect(self._q_clear); tb.addWidget(cb)
        self._q_clear_btn=cb
        l.addLayout(tb)
        self.qlist=QListWidget(); self.qlist.setObjectName("songList")
        self.q_delegate=TrackDelegate(self, rows=lambda: self.queue, current=lambda: self.qidx)
        self.qlist.setItemDelegate(self.q_delegate)
        self.qlist.setMouseTracking(True); self.qlist.setUniformItemSizes(True)
        self.qlist.itemDoubleClicked.connect(lambda it: self._q_jump(it.data(Qt.UserRole)))
        self.qlist.setContextMenuPolicy(Qt.CustomContextMenu); self.qlist.customContextMenuRequested.connect(self._q_ctx)
        l.addWidget(self.qlist)
        return w

    # ===== v15: Settings page =====
    def _settings_view(self):
        w=QWidget(); outer=QVBoxLayout(w); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        t=QLabel("Settings"); t.setObjectName("pageTitle"); outer.addWidget(t)
        s=QLabel("Personalize Aurora"); s.setObjectName("pageSubtitle"); outer.addWidget(s)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        body=QWidget(); bl=QVBoxLayout(body); bl.setContentsMargins(28,4,28,24); bl.setSpacing(14)
        def card(title, desc, icon):
            c=QFrame(); c.setObjectName("settingsCard")
            cl=QVBoxLayout(c); cl.setContentsMargins(20,16,20,18); cl.setSpacing(10)
            h=QHBoxLayout(); h.setSpacing(10)
            ic=QLabel(); ic.setPixmap(_svg(icon,M3["primary"]).pixmap(22,22)); ic.setFixedSize(24,24); h.addWidget(ic)
            tt=QLabel(title); tt.setObjectName("cardTitle"); h.addWidget(tt); h.addStretch(); cl.addLayout(h)
            dd=QLabel(desc); dd.setObjectName("cardDesc"); dd.setWordWrap(True); cl.addWidget(dd)
            bl.addWidget(c); return c,cl,ic
        # --- Theme color card ---
        c1,c1l,self._theme_icon=card("Theme color","Drag the slider — the whole Material 3 palette regenerates live from that hue. Every surface, button and the beat graph follow.",IC_PALETTE)
        hs=QHBoxLayout(); hs.setSpacing(14)
        self.hue_slider=ClickSlider(Qt.Horizontal); self.hue_slider.setObjectName("hueSlider")
        self.hue_slider.setRange(0,359); self.hue_slider.setValue(int(self.cfg.get("theme_hue",DEFAULT_HUE))%360)
        self.hue_slider.setCursor(Qt.PointingHandCursor)
        self.hue_slider.valueChanged.connect(self._hue_changed)
        hs.addWidget(self.hue_slider,stretch=1)
        self.hue_chip=QLabel(); self.hue_chip.setFixedSize(36,36)
        hs.addWidget(self.hue_chip)
        c1l.addLayout(hs)
        rs=QHBoxLayout()
        rst=QPushButton("  Reset to Aurora Indigo"); rst.setObjectName("tonalBtn"); rst.setIcon(_svg(IC_REFRESH,M3["on_secondary_container"])); rst.setCursor(Qt.PointingHandCursor)
        rst.clicked.connect(lambda: self.hue_slider.setValue(DEFAULT_HUE)); rs.addWidget(rst); rs.addStretch(); c1l.addLayout(rs)
        self._theme_reset_btn=rst
        # --- Beat graph card ---
        c2,c2l,self._viz_icon=card("Beat graph","SoundCloud-style animated waveform above the player bar. Bars bounce with the actual beat; click it to seek. Turn off to save a little CPU.",IC_EQ)
        vt=QPushButton("  Beat graph: ON" if self.cfg.get("show_viz",True) else "  Beat graph: OFF")
        vt.setObjectName("tonalBtn"); vt.setCheckable(True); vt.setChecked(bool(self.cfg.get("show_viz",True)))
        vt.setIcon(_svg(IC_CHECK,M3["on_secondary_container"])); vt.setCursor(Qt.PointingHandCursor)
        vt.clicked.connect(self._viz_toggle); self.viz_btn=vt
        vh=QHBoxLayout(); vh.addWidget(vt); vh.addStretch(); c2l.addLayout(vh)
        # v17.3: Visualizer mode dropdown (inside the Beat graph card)
        viz_cfg = load_viz_config()
        vm_row = QHBoxLayout(); vm_row.setSpacing(8)
        vm_lbl = QLabel("Graph type:"); vm_lbl.setObjectName("cardDesc"); vm_row.addWidget(vm_lbl)
        self.viz_mode_combo = QComboBox(); self.viz_mode_combo.setObjectName("sortCombo")
        for mode_name in VIZ_MODES:
            self.viz_mode_combo.addItem(mode_name)
        self.viz_mode_combo.setCurrentIndex(viz_cfg.get("mode", VIZ_DEFAULT_MODE))
        self.viz_mode_combo.currentIndexChanged.connect(self._on_viz_mode_changed)
        vm_row.addWidget(self.viz_mode_combo)
        vm_row.addStretch()
        c2l.addLayout(vm_row)
        # v17.3: Bar width + gap spinboxes (only relevant for Bars/Mirror/Blocks modes)
        bw_row = QHBoxLayout(); bw_row.setSpacing(8)
        bw_lbl = QLabel("Bar width:"); bw_lbl.setObjectName("cardDesc"); bw_row.addWidget(bw_lbl)
        self.viz_bar_width_spin = QSpinBox(); self.viz_bar_width_spin.setRange(1, 20)
        self.viz_bar_width_spin.setValue(viz_cfg.get("bar_width", 4))
        self.viz_bar_width_spin.valueChanged.connect(self._on_viz_param_changed)
        bw_row.addWidget(self.viz_bar_width_spin)
        bg_lbl = QLabel("Gap:"); bg_lbl.setObjectName("cardDesc"); bw_row.addWidget(bg_lbl)
        self.viz_bar_gap_spin = QSpinBox(); self.viz_bar_gap_spin.setRange(0, 20)
        self.viz_bar_gap_spin.setValue(viz_cfg.get("bar_gap", 2))
        self.viz_bar_gap_spin.valueChanged.connect(self._on_viz_param_changed)
        bw_row.addWidget(self.viz_bar_gap_spin)
        rounded_chk = QCheckBox("Rounded"); rounded_chk.setChecked(viz_cfg.get("rounded", True))
        rounded_chk.stateChanged.connect(self._on_viz_param_changed)
        bw_row.addWidget(rounded_chk); self.viz_rounded_chk = rounded_chk
        bw_row.addStretch()
        c2l.addLayout(bw_row)
        # --- Audio device card ---
        c3,c3l,self._dev_icon=card("Audio output","Pick which speaker/headphones Aurora uses. Bluetooth devices reconnect automatically.",IC_AUDIO_DEVICE)
        dv=QPushButton("  Choose Audio Device"); dv.setObjectName("tonalBtn"); dv.setIcon(_svg(IC_AUDIO_DEVICE,M3["on_secondary_container"])); dv.setCursor(Qt.PointingHandCursor)
        dv.clicked.connect(self._show_device_selector)
        self._dev_choose_btn=dv
        dh=QHBoxLayout(); dh.addWidget(dv); dh.addStretch(); c3l.addLayout(dh)
        # --- v16.6: YouTube Auth card (bot-protection bypass) ---
        c5,c5l,self._yt_auth_icon = card("YouTube Auth (v16.6)",
            "Browse downloads use multi-strategy bot-protection bypass: cookies-from-browser → "
            "cookies.txt → client-type rotation → Invidious → SAPISIDHASH Innertube → plain yt-dlp. "
            "Configure a strategy below to make downloads succeed even on bot-protected videos.",
            IC_CLOUD)
        # Strategy dropdown
        strat_row = QHBoxLayout(); strat_row.setSpacing(10)
        strat_lbl = QLabel("Strategy:"); strat_lbl.setObjectName("cardDesc")
        strat_row.addWidget(strat_lbl)
        self.yt_strategy_combo = QComboBox(); self.yt_strategy_combo.setObjectName("sortCombo")
        self.yt_strategy_combo.addItem("Auto (try all in order)", "auto")
        self.yt_strategy_combo.addItem("Browser cookies (--cookies-from-browser)", "browser")
        self.yt_strategy_combo.addItem("cookies.txt file (--cookies)", "cookies_file")
        self.yt_strategy_combo.addItem("SAPISIDHASH Innertube (direct API)", "innertube")
        self.yt_strategy_combo.addItem("No auth (client-rotation + Invidious only)", "none")
        saved_strat = self.cfg.get("yt_auth_strategy", "auto")
        idx = max(0, self.yt_strategy_combo.findData(saved_strat))
        self.yt_strategy_combo.setCurrentIndex(idx)
        self.yt_strategy_combo.currentIndexChanged.connect(self._on_yt_strategy_changed)
        strat_row.addWidget(self.yt_strategy_combo, stretch=1)
        c5l.addLayout(strat_row)
        # Browser picker (for cookies-from-browser strategy)
        browser_row = QHBoxLayout(); browser_row.setSpacing(10)
        browser_lbl = QLabel("Browser:"); browser_lbl.setObjectName("cardDesc")
        browser_row.addWidget(browser_lbl)
        self.yt_browser_combo = QComboBox(); self.yt_browser_combo.setObjectName("sortCombo")
        for b in YTDLP_BROWSER_CHOICES:
            self.yt_browser_combo.addItem(b, b)
        saved_browser = self.cfg.get("yt_browser_choice", "firefox")
        idx = max(0, self.yt_browser_combo.findData(saved_browser))
        self.yt_browser_combo.setCurrentIndex(idx)
        self.yt_browser_combo.currentIndexChanged.connect(self._on_yt_browser_changed)
        browser_row.addWidget(self.yt_browser_combo)
        browser_row.addStretch()
        c5l.addLayout(browser_row)
        # cookies.txt file picker
        file_row = QHBoxLayout(); file_row.setSpacing(8)
        self.yt_cookies_file_btn = QPushButton("  Choose cookies.txt…")
        self.yt_cookies_file_btn.setObjectName("tonalBtn")
        self.yt_cookies_file_btn.setIcon(_svg(IC_OPEN_EXTERNAL, M3["on_secondary_container"]))
        self.yt_cookies_file_btn.setCursor(Qt.PointingHandCursor)
        self.yt_cookies_file_btn.clicked.connect(self._on_yt_cookies_file_pick)
        file_row.addWidget(self.yt_cookies_file_btn)
        self.yt_cookies_file_lbl = QLabel(self.cfg.get("yt_cookies_file", "") or "(none)")
        self.yt_cookies_file_lbl.setObjectName("cardDesc")
        self.yt_cookies_file_lbl.setWordWrap(True)
        file_row.addWidget(self.yt_cookies_file_lbl, stretch=1)
        c5l.addLayout(file_row)
        # SAPISID cookie string (for Innertube strategy)
        cookie_row = QHBoxLayout(); cookie_row.setSpacing(8)
        cookie_lbl = QLabel("SAPISID cookie:"); cookie_lbl.setObjectName("cardDesc")
        cookie_row.addWidget(cookie_lbl)
        self.yt_cookies_str_edit = QLineEdit()
        self.yt_cookies_str_edit.setPlaceholderText("Paste full Cookie header (SAPISID=...; __Secure-1PAPISID=...)")
        self.yt_cookies_str_edit.setText(self.cfg.get("yt_cookies_str", ""))
        self.yt_cookies_str_edit.setStyleSheet(_m3ss(
            "QLineEdit { background:@surface_container_low; border:1px solid @outline_variant; "
            "border-radius:8px; padding:8px 12px; color:@on_surface; }"))
        self.yt_cookies_str_edit.editingFinished.connect(self._on_yt_cookies_str_changed)
        cookie_row.addWidget(self.yt_cookies_str_edit, stretch=1)
        c5l.addLayout(cookie_row)
        # Auth status display
        self._update_yt_auth_status()
        # --- About card ---
        c4,c4l,_=card("About",
            f"Aurora Music Player v{APP_VERSION}\n"
            f"Compatible with agent. CLI available.\n"
            f"Library: ~/Downloads/ (auto-scan, F5 to refresh).\n"
            f"Agent-controllable via playerctl or aurora-player CLI.",
            IC_MUSIC)
        bl.addStretch()
        scroll.setWidget(body); outer.addWidget(scroll)
        self._update_hue_chip()
        return w

    # ===== v16.6: YouTube Auth settings handlers =====
    def _on_yt_strategy_changed(self):
        strat = self.yt_strategy_combo.currentData() or "auto"
        self.cfg["yt_auth_strategy"] = strat; save_cfg(self.cfg)
        self._update_yt_auth_status()
        print(f"[Aurora][v16.6] YouTube auth strategy: {strat}", flush=True)

    def _on_yt_browser_changed(self):
        browser = self.yt_browser_combo.currentData() or "firefox"
        self.cfg["yt_browser_choice"] = browser; save_cfg(self.cfg)
        print(f"[Aurora][v16.6] YouTube cookies-from-browser: {browser}", flush=True)

    def _on_yt_cookies_file_pick(self):
        """Open a file picker for the user to choose a cookies.txt (Netscape format)."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose cookies.txt (Netscape format)", str(Path.home()),
            "Cookies files (*.txt);;All files (*)")
        if path:
            self.cfg["yt_cookies_file"] = path; save_cfg(self.cfg)
            self.yt_cookies_file_lbl.setText(path)
            self._update_yt_auth_status()
            print(f"[Aurora][v16.6] cookies.txt set: {path}", flush=True)

    def _on_yt_cookies_str_changed(self):
        cookies_str = self.yt_cookies_str_edit.text().strip()
        self.cfg["yt_cookies_str"] = cookies_str; save_cfg(self.cfg)
        self._update_yt_auth_status()
        print(f"[Aurora][v16.6] SAPISID cookie string updated ({len(cookies_str)} chars)", flush=True)

    def _update_yt_auth_status(self):
        """v16.6: refresh the auth status display based on current cfg."""
        # No dedicated label widget — just log to console. Could add a status
        # QLabel here in the future if needed.
        try:
            strat = self.cfg.get("yt_auth_strategy", "auto")
            browser = self.cfg.get("yt_browser_choice", "firefox")
            cookies_file = self.cfg.get("yt_cookies_file", "")
            cookies_str = self.cfg.get("yt_cookies_str", "")
            print(f"[Aurora][v16.6] Auth status: strategy={strat} browser={browser} "
                  f"cookies_file={'set' if cookies_file else 'none'} "
                  f"cookies_str={'set' if cookies_str else 'none'}", flush=True)
        except Exception: pass

    def _on_f5_refresh(self):
        """v16.7: context-aware F5 refresh.
        - On Library page: rescan ~/Downloads/ (same as v14 behavior).
        - On Browse page: re-fire the current search (fixes the 'search doesn't
          work, have to keep refreshing' complaint — F5 now actually refreshes
          the Browse results, not just the library)."""
        if self.stack.currentIndex() == 1:  # Browse page
            if hasattr(self, "browse_search"):
                q = self.browse_search.text().strip()
                if q:
                    self._browse_debounce.stop()
                    self._fire_browse_search()
                    print(f"[Aurora][Browse] F5 — re-firing search: {q!r}", flush=True)
                else:
                    # Empty search — load a fresh seed
                    self._browse_initial_loaded = False
                    self._browse_load_initial()
        else:
            # Library or other pages — rescan
            self.scan()

    def _shortcuts(self):
        from PySide6.QtGui import QShortcut, QKeySequence
        # Playback
        QShortcut(QKeySequence(Qt.Key_Space),self,self.toggle)
        QShortcut(QKeySequence("Ctrl+P"),self,self.toggle)       # v17.3: Ctrl+P toggle
        QShortcut(QKeySequence(Qt.Key_Right),self,self.next)
        QShortcut(QKeySequence(Qt.Key_Left),self,self.prev)
        QShortcut(QKeySequence("Ctrl+Right"),self,self.next)     # v17.3: Ctrl+arrow
        QShortcut(QKeySequence("Ctrl+Left"),self,self.prev)      # v17.3: Ctrl+arrow
        QShortcut(QKeySequence("Ctrl+S"),self,self.stop)         # v17.3: Ctrl+S stop
        # Volume
        QShortcut(QKeySequence(Qt.Key_Up),self,lambda:self.vol.setValue(min(100,self.vol.value()+5)))
        QShortcut(QKeySequence(Qt.Key_Down),self,lambda:self.vol.setValue(max(0,self.vol.value()-5)))
        QShortcut(QKeySequence("Ctrl+Up"),self,lambda:self.vol.setValue(min(100,self.vol.value()+10)))   # v17.3
        QShortcut(QKeySequence("Ctrl+Down"),self,lambda:self.vol.setValue(max(0,self.vol.value()-10)))   # v17.3
        QShortcut(QKeySequence("Ctrl+M"),self,self._mute_toggle) # v17.3: Ctrl+M mute
        # Seek
        QShortcut(QKeySequence("Shift+Right"),self,lambda:self.player.setPosition(min(self.player.duration(),self.player.position()+10000)))  # v17.3: +10s
        QShortcut(QKeySequence("Shift+Left"),self,lambda:self.player.setPosition(max(0,self.player.position()-10000)))   # v17.3: -10s
        # Navigation
        QShortcut(QKeySequence("Ctrl+F"),self,lambda:self.srch.setFocus() if self.stack.currentIndex()==0 else (self.browse_search.setFocus() if self.stack.currentIndex()==1 else None))
        QShortcut(QKeySequence("Ctrl+1"),self,lambda:self._switch("library"))    # v17.3: Ctrl+1-7 page nav
        QShortcut(QKeySequence("Ctrl+2"),self,lambda:self._switch("browse"))
        QShortcut(QKeySequence("Ctrl+3"),self,lambda:self._switch("history"))
        QShortcut(QKeySequence("Ctrl+4"),self,lambda:self._switch("equalizer"))
        QShortcut(QKeySequence("Ctrl+5"),self,lambda:self._switch("playlists"))
        QShortcut(QKeySequence("Ctrl+6"),self,lambda:self._switch("queue"))
        QShortcut(QKeySequence("Ctrl+7"),self,lambda:self._switch("settings"))
        QShortcut(QKeySequence(Qt.Key_Escape),self,self.stop)
        QShortcut(QKeySequence(Qt.Key_F5),self,self._on_f5_refresh)
        QShortcut(QKeySequence("Ctrl+R"),self,self._shuf)        # v17.3: Ctrl+R shuffle toggle
        QShortcut(QKeySequence("Ctrl+E"),self,self._rep)         # v17.3: Ctrl+E repeat toggle
        # v15: Delete removes the selected queue row (only when queue focused)
        sc=QShortcut(QKeySequence(Qt.Key_Delete),self.qlist,self._q_remove_sel)
        sc.setContext(Qt.WidgetShortcut)

    def _tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self.tray=QSystemTrayIcon()
        # Set icon before showing (prevents "No Icon set" warning)
        icon = QIcon.fromTheme("audio-x-generic")
        if icon.isNull():
            pm = QPixmap(24, 24); pm.fill(Qt.transparent)
            p = QPainter(pm); p.setBrush(QColor(M3["primary"])); p.drawEllipse(4,4,16,16); p.end()
            icon = QIcon(pm)
        self.tray.setIcon(icon)
        self.tray.setToolTip(APP_NAME)
        m=QMenu()
        for txt,fn in [("Play/Pause",self.toggle),("Next",self.next),("Previous",self.prev)]:
            a=QAction(txt,self); a.triggered.connect(fn); m.addAction(a)
        m.addSeparator(); a=QAction("Quit",self); a.triggered.connect(self.close); m.addAction(a)
        self.tray.setContextMenu(m); self.tray.activated.connect(lambda r: self.show() if r==QSystemTrayIcon.Trigger else None); self.tray.show()

    def _switch(self,v):
        for k,b in self.navs.items(): b.setChecked(k==v)
        # v17.0: stack indices — Library=0, Browse=1, History=2, Equalizer=3, Playlists=4, Queue=5, Settings=6
        if v=="library": self.stack.setCurrentIndex(0)
        elif v=="browse": self.stack.setCurrentIndex(1); self._browse_focus_search()
        elif v=="history": self.stack.setCurrentIndex(2); self._refresh_history()
        elif v=="equalizer": self.stack.setCurrentIndex(3); self._refresh_equalizer()
        elif v=="playlists": self.stack.setCurrentIndex(4); self._refpl()
        elif v=="queue": self.stack.setCurrentIndex(5); self._refq()
        elif v=="settings": self.stack.setCurrentIndex(6)

    def scan(self):
        # v12.2: don't replace a scanner that is still running — destroying a
        # live QThread crashes the whole app ("QThread destroyed while running").
        if getattr(self,'sc',None) is not None and self.sc.isRunning(): return
        if hasattr(self,'sub'): self.sub.setText("Scanning ~/Downloads/...")
        self.sc=Scanner(); self.sc.done.connect(self._scan_done); self.sc.start()

    def _scan_done(self,songs):
        old=self.cur["path"] if self.cur else None
        self.songs=songs; self._apply_sort(); self._refresh()
        if hasattr(self,'sub'): self.sub.setText(f"{len(songs)} songs in ~/Downloads/")
        if old:
            for i,s in enumerate(self.songs):
                if s["path"]==old: self.cur_idx=i; self.cur=self.songs[i]; break

    def _apply_sort(self):
        if self.sort==SortMode.TITLE: self.songs.sort(key=lambda s:s["title"].lower())
        elif self.sort==SortMode.ARTIST: self.songs.sort(key=lambda s:s["artist"].lower())
        elif self.sort==SortMode.ALBUM: self.songs.sort(key=lambda s:s["album"].lower())
        else: self.songs.sort(key=lambda s:s.get("date",0),reverse=True)

    def _refresh(self):
        tx=self.srch.text().lower() if hasattr(self,'srch') else ""
        self.slist.clear()
        for i,s in enumerate(self.songs):
            if tx and tx not in f"{s['title']} {s['artist']} {s['album']}".lower(): continue
            d=fmt_time(s["duration"]) if s["duration"] else ""
            txt=f"  {s['title']}  -  {s['artist']}" + (f"  .  {d}" if d else "")
            item=QListWidgetItem(txt); item.setData(Qt.UserRole,i)
            if i==self.cur_idx: item.setSelected(True)
            self.slist.addItem(item)

    def _click(self,item): self.play_idx(item.data(Qt.UserRole))
    def _ctx(self,pos):
        item=self.slist.itemAt(pos)
        if not item: return
        idx=item.data(Qt.UserRole); m=QMenu()
        for txt,fn in [("Play",lambda:self.play_idx(idx)),("Add to queue (next)",lambda:self._q_add(idx,True)),("Add to queue (last)",lambda:self._q_add(idx,False))]:
            a=QAction(txt,self); a.triggered.connect(fn); m.addAction(a)
        # v15: THE missing "Add to playlist" submenu
        sub=m.addMenu("Add to playlist")
        path=self.songs[idx]["path"]
        for name in self.playlists:
            a=QAction(name,self); a.triggered.connect(lambda _,n=name: self.add_to_playlist(n,path)); sub.addAction(a)
        if self.playlists: sub.addSeparator()
        a=QAction("New playlist...",self)
        a.triggered.connect(lambda: (lambda n: self.add_to_playlist(n,path) if n else None)(self._newpl()))
        sub.addAction(a)
        m.exec(self.slist.mapToGlobal(pos))

    def _q_add(self,idx,nxt):
        if nxt: self.queue.insert(self.qidx+1,self.songs[idx])
        else: self.queue.append(self.songs[idx])
        self._refq()

    def _was_song_played_before(self, path, title):
        """v17.0: Check if a song was played before (exists in history)."""
        try:
            h = load_history()
            for e in h.get("entries", []):
                if path and e.get("path") == path: return True
                if not path and e.get("title") == title: return True
            return False
        except Exception:
            return False

    def _update_repeat_info(self):
        """v17.2: Stats moved to History page — this is now a no-op stub.
        The repeat/skip/date/time stats are shown inside the History page's
        stats panel (see _refresh_history + _history_view), NOT in the player
        bar. This method is kept for backward compat (called from play_idx)."""
        pass  # v17.2: stats are in History page now, not player bar

    def play_idx(self,idx):
        if idx<0 or idx>=len(self.songs): return
        self.cur_idx=idx; self.cur=self.songs[idx]
        # v17.5: Reset A-B loop when song changes
        if hasattr(self, '_ab_looping') and self._ab_looping:
            self._ab_clear()
        self.tl.setText(self.cur["title"]); self.al.setText(self.cur["artist"])
        img=None
        if self.cur.get("art"):
            im=QImage()
            if im.loadFromData(self.cur["art"]) and not im.isNull(): img=im
        if img:
            pm=QPixmap.fromImage(img.scaled(64,64,Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation)).copy(0,0,64,64)
            self.art.setPixmap(_rounded_pixmap(pm,12))
        else:
            self.art.clear(); self.art.setText("\u266B")
        self.backdrop.set_art(img)  # v13: blurred album-art backdrop
        self._refresh()
        # v15: keep the queue/playlist views' now-playing highlight in sync
        self.qlist.viewport().update(); self.pl_songlist.viewport().update()
        # v15: beat graph — instant pseudo waveform, swapped for real levels
        # as soon as the async QAudioDecoder scan finishes
        self.viz.set_levels(pseudo_levels(self.cur["path"], self.cur["duration"]), False)
        if self.cfg.get("show_viz",True): self.lv_scanner.scan(self.cur["path"])
        print(f"[Aurora] play_idx: {idx}, path: {self.cur['path']}", flush=True)
        # v13 FIX: the old code called setSource() while audio was still
        # playing (audible CLICK/pop — abrupt waveform cutoff) and then
        # waited an arbitrary 300ms before play() (felt laggy). Now:
        # mute -> stop -> swap source -> play -> ~120ms volume fade-in.
        self.audio.setVolume(0.0)
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(self.cur["path"]))
        self.player.play()
        self.playing=True; self.pp.setIcon(self._ai); self.mpris.update()
        self._fade_in()
        if hasattr(self,'tray') and self.tray.isVisible(): self.tray.showMessage(APP_NAME,f"Now playing: {self.cur['title']}")
        self.cfg["last"]=idx; save_cfg(self.cfg)
        # v16.8: record this play in history (title, artist, path, play count)
        try:
            record_play(self.cur.get("title",""), self.cur.get("artist",""),
                        self.cur.get("path",""), self.cur.get("duration",0))
        except Exception as e:
            print(f"[Aurora][History] record_play failed: {e}", flush=True)
        # v17.0: record repeat count (if this song was played before, it's a repeat)
        try:
            path = self.cur.get("path", "")
            title = self.cur.get("title", "")
            repeat_count = get_song_repeat_count(path, title)
            # If repeat_count > 0, this is a repeat (the song was played before)
            # Increment the repeat counter
            if repeat_count > 0 or self._was_song_played_before(path, title):
                record_repeat(path, title)
        except Exception as e:
            print(f"[Aurora][Repeat] record failed: {e}", flush=True)
        # v17.0: update the repeat info label in the player bar
        self._update_repeat_info()
        # v17.0: start the AnimatedNowPlaying + EQ animation
        if hasattr(self, "now_playing_anim"):
            self.now_playing_anim.set_playing(True)
        if hasattr(self, "eq_widget"):
            self.eq_widget.set_playing(True)

    def play_file(self,fp):
        fp=Path(fp)
        if not fp.exists():
            print(f"[Aurora] File not found: {fp}", flush=True)
            return
        print(f"[Aurora] play_file called: {fp}", flush=True)
        # Find in library
        for i,s in enumerate(self.songs):
            if s["path"]==str(fp):
                print(f"[Aurora] Found in library at index {i}", flush=True)
                self.play_idx(i)
                return
        # Not in library yet - the file was just downloaded and Aurora's
        # 30s rescan hasn't fired. Trigger an async rescan AND insert the
        # new song manually so playback starts immediately.
        print(f"[Aurora] Not in library, adding + triggering rescan...", flush=True)
        try:
            meta = get_metadata(fp)
        except Exception as e:
            print(f"[Aurora] Metadata read failed ({e}); using minimal info.", flush=True)
            meta = {"title":fp.stem,"artist":"Unknown","album":"","duration":0,"art":None,"path":str(fp),"date":fp.stat().st_mtime}
        # Avoid duplicate insertion if rescan already added it
        if not any(s["path"]==str(fp) for s in self.songs):
            self.songs.insert(0, meta)
        self._apply_sort()
        self._refresh()
        # Find the new index after sort
        new_idx = next((i for i,s in enumerate(self.songs) if s["path"]==str(fp)), 0)
        self.play_idx(new_idx)
        # Async rescan to pick up any other new files in ~/Downloads/
        self.scan()

    def play(self):
        # v12.2: 'play' with nothing selected used to silently do NOTHING,
        # so a fresh 'playerctl --player=aurora play' looked broken. Now it
        # falls back to the most recent song in the library.
        if not self.cur:
            if self.songs: self.play_idx(0)
            return
        self.player.play(); self.playing=True; self.pp.setIcon(self._ai); self.mpris.update()
    def pause(self):
        self.player.pause(); self.playing=False; self.pp.setIcon(self._pi); self.mpris.update()
    def toggle(self):
        # v12.2: decide from the REAL playback state, not the drift-prone flag
        self.pause() if self.player.playbackState()==QMediaPlayer.PlayingState else self.play()
    def stop(self):
        self.player.stop(); self.playing=False; self.pp.setIcon(self._pi); self.seek.setValue(0); self.mpris.update()
        # v17.0: stop animations
        if hasattr(self, "now_playing_anim"): self.now_playing_anim.set_playing(False)
        if hasattr(self, "eq_widget"): self.eq_widget.set_playing(False)
    def next(self):
        # v17.0: record skip-forward
        try: record_skip("forward")
        except Exception: pass
        # v15: queue entries play even if not (yet) in the library, and the
        # queue view highlight follows along
        if self.queue and self.qidx<len(self.queue)-1:
            self.qidx+=1; self._play_song(self.queue[self.qidx]); self._refq()
        elif self.shuffle and len(self.songs)>1:
            # v12.2: manual 'next' now honors shuffle (used to only apply at end of track)
            import random
            idx=random.randrange(len(self.songs))
            if idx==self.cur_idx: idx=(idx+1)%len(self.songs)
            self.play_idx(idx)
        elif 0<=self.cur_idx<len(self.songs)-1: self.play_idx(self.cur_idx+1)
        elif self.repeat==RepeatMode.ALL and self.songs: self.play_idx(0)
    def _on_remote_cmd(self,cmd,arg):
        # v12.2: single main-thread entry point for MPRIS + file IPC commands
        try:
            if cmd=="play": self.play()
            elif cmd=="pause": self.pause()
            elif cmd=="toggle": self.toggle()
            elif cmd=="stop": self.stop()
            elif cmd=="next": self.next()
            elif cmd=="prev": self.prev()
            elif cmd=="seek": self.player.setPosition(max(0,self.player.position()+int(arg)))
            elif cmd=="setpos": self.player.setPosition(max(0,int(arg)))
            elif cmd=="volume": self.vol.setValue(max(0,min(100,int(float(arg)*100))))
            elif cmd=="play-file": self.play_file(arg)
            # ===== v15: queue / playlist / theme agent commands =====
            elif cmd=="queue-file":
                self.queue.append(self._resolve(arg)); self._refq()
            elif cmd=="queue-next-file":
                self.queue.insert(min(self.qidx+1,len(self.queue)),self._resolve(arg)); self._refq()
            elif cmd=="queue-remove": self.q_remove(int(arg)-1)  # 1-based for humans/agents
            elif cmd=="queue-clear": self._q_clear()
            elif cmd=="new-playlist": self._newpl(arg)
            elif cmd=="add-to-playlist":
                name,path=arg.split("\n",1); self.add_to_playlist(name,path)
            elif cmd=="play-playlist":
                if not self.play_playlist(arg):
                    print(f"[Aurora] play-playlist: '{arg}' not found or empty", flush=True)
            elif cmd=="set-theme":
                self.hue_slider.setValue(int(arg)%360)
            # ===== v16: Browse agent commands =====
            elif cmd=="browse-search":
                # Switch to Browse page + run query
                self._switch("browse")
                self.browse_search.setText(arg)
                self._browse_debounce.stop()
                self._fire_browse_search()
            elif cmd=="browse-country":
                # Switch iTunes storefront: arg = "US" / "IN" / "GB" / ...
                idx = self.browse_country.findData(arg.upper())
                if idx >= 0: self.browse_country.setCurrentIndex(idx)
            elif cmd=="browse-preview":
                # v16.5: DEPRECATED — preview button removed per user request.
                # Kept for backward-compat with agents that still send it; logs a hint.
                print("[Aurora] browse-preview is deprecated in v16.5 (preview button removed). "
                      "Use browse-download for full-track download.", flush=True)
            elif cmd=="browse-load-more":
                # v16.5: trigger the next page of results (infinite scroll) via IPC.
                self._fire_browse_load_more()
            elif cmd=="browse-download":
                # v16.5: full-track download by trackId from current results.
                # Uses yt-dlp + ffmpeg (NOT the 30-sec iTunes preview).
                tid = arg.strip()
                for t in (self._browse_results or []):
                    if t.track_id == tid:
                        self._browse_download(t); break
                else:
                    print(f"[Aurora] browse-download: trackId '{tid}' not in current results", flush=True)
            self.mpris.update()
        except Exception as e: print(f"[Aurora] remote_cmd error ({cmd}): {e}", flush=True)
    def _setup_audio_buffer_output(self):
        """v17.5: Set up QAudioBufferOutput for REAL-TIME audio sync.
        QAudioBufferOutput (Qt 6.8+) gives us live decoded PCM audio buffers
        from QMediaPlayer as the song plays. We compute FFT on each buffer
        with numpy and feed the spectrum bars to the Visualizer.
        This makes ALL visualizer modes (Bars, Mirror, Wave, Radial, Blocks)
        literally move with the actual audio output — true sync, like CAVA."""
        try:
            import numpy as np
            self._np = np
            self._fft_window = np.hanning(2048)  # pre-compute Hann window
            self._fft_bars_count = 48  # number of spectrum bars to output
            self._audio_buf_out = QAudioBufferOutput()
            self.player.setAudioBufferOutput(self._audio_buf_out)
            self._audio_buf_out.audioBufferReceived.connect(self._on_audio_buffer)
            print("[Aurora][v17.5] QAudioBufferOutput initialized — live audio sync ACTIVE", flush=True)
        except Exception as e:
            print(f"[Aurora][v17.5] QAudioBufferOutput unavailable: {e} — falling back to pre-computed levels", flush=True)
            self._audio_buf_out = None
            self._np = None

    def _on_audio_buffer(self, buf):
        """v17.5: Receive a live audio buffer from QAudioBufferOutput.
        Compute FFT → spectrum bars → feed to Visualizer.
        This is called on the Qt main thread for every audio buffer (~20-40ms
        depending on the audio format). numpy FFT on 2048 samples takes ~0.1ms."""
        if not hasattr(self, '_np') or self._np is None: return
        try:
            np = self._np
            # Get the raw audio data from the buffer
            data = bytes(buf.data())
            if not data: return
            # Determine the sample format from the buffer's format
            fmt = buf.format()
            sample_format = fmt.sampleFormat()
            if sample_format == QAudioFormat.SampleFormat.Float:
                samples = np.frombuffer(data, dtype=np.float32)
            elif sample_format == QAudioFormat.SampleFormat.Int16:
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            elif sample_format == QAudioFormat.SampleFormat.Int32:
                samples = np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                samples = np.frombuffer(data, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
            # If stereo, mix to mono
            channels = fmt.channelCount()
            if channels > 1 and len(samples) > channels:
                samples = samples[:len(samples) // channels * channels].reshape(-1, channels).mean(axis=1)
            # Need at least 2048 samples for a good FFT
            if len(samples) < 256: return
            # Take the most recent 2048 samples (or pad if shorter)
            chunk = samples[-2048:] if len(samples) >= 2048 else np.pad(samples, (2048 - len(samples), 0))
            # Apply Hann window to reduce spectral leakage
            windowed = chunk * self._fft_window
            # Compute FFT (real → complex)
            fft = np.abs(np.fft.rfft(windowed))
            # Map to log-frequency bars (like CAVA does)
            n_bins = len(fft)
            if n_bins < 2: return
            # Log-spaced bin boundaries
            min_freq = 20  # 20Hz
            max_freq = min(fmt.sampleRate() / 2, 16000)  # 16kHz or Nyquist
            if max_freq <= min_freq: return
            bin_freqs = np.linspace(0, fmt.sampleRate() / 2, n_bins)
            # Find indices for log-spaced bars
            log_freqs = np.logspace(np.log10(min_freq), np.log10(max_freq), self._fft_bars_count + 1)
            bars = []
            for i in range(self._fft_bars_count):
                lo = np.searchsorted(bin_freqs, log_freqs[i])
                hi = np.searchsorted(bin_freqs, log_freqs[i + 1])
                if hi <= lo: hi = lo + 1
                band = fft[lo:hi]
                val = float(band.mean()) if len(band) > 0 else 0.0
                bars.append(val)
            # Normalize to 0.0-1.0
            max_val = max(bars) if bars else 1.0
            if max_val > 0:
                bars = [min(1.0, b / max_val * 1.5) for b in bars]  # *1.5 for visual boost
            else:
                bars = [0.0] * self._fft_bars_count
            # Feed to Visualizer
            if hasattr(self, 'viz'):
                self.viz.set_spectrum(bars)
        except Exception as e:
            pass  # never crash the audio thread

    def _state_changed(self,st):
        self.playing = (st==QMediaPlayer.PlayingState)
        self.pp.setIcon(self._ai if self.playing else self._pi)
        # v15: motion graphics follow the real playback state
        self.viz.set_playing(self.playing)
        (self.eq_timer.start() if self.playing else self.eq_timer.stop())
        if not self.playing: self._eq_tick()  # one last repaint to freeze the badge
        # v17.0: AnimatedNowPlaying + Equalizer animation follow playback state
        if hasattr(self, "now_playing_anim"):
            self.now_playing_anim.set_playing(self.playing)
        if hasattr(self, "eq_widget"):
            self.eq_widget.set_playing(self.playing)
        self._write_status()
        if hasattr(self,'mpris'): self.mpris.update()
    def _levels_done(self,path,levels):
        """v15: real waveform arrived from QAudioDecoder — swap it in."""
        if self.cur and self.cur["path"]==path and len(levels)>=24:
            self.viz.set_levels(levels,True)
    def _eq_tick(self):
        """v15: ~8fps repaint of visible lists so the EQ badge dances."""
        for lw in (self.slist,self.qlist,self.pl_songlist):
            if lw.isVisible(): lw.viewport().update()
    def _write_status(self):
        # v12.2: machine-readable status so the agent can check what's playing
        # even without playerctl (read via: aurora-player --status)
        try:
            st=self.player.playbackState()
            s="playing" if st==QMediaPlayer.PlayingState else ("paused" if st==QMediaPlayer.PausedState else "stopped")
            STATUS_FILE.write_text(json.dumps({
                "state":s,
                "title":self.cur["title"] if self.cur else "",
                "artist":self.cur["artist"] if self.cur else "",
                "path":self.cur["path"] if self.cur else "",
                "position_sec":int(self.player.position()/1000),
                "duration_sec":self.cur["duration"] if self.cur else 0,
                # v15: richer status for the agent
                "queue":[{"title":s["title"],"artist":s["artist"],"path":s["path"]} for s in self.queue[:100]],
                "queue_index":self.qidx if self.queue else -1,
                "queue_length":len(self.queue),
                "playlists":{n:len(self._pl_paths(n)) for n in self.playlists},
                "theme_hue":int(self.cfg.get("theme_hue",DEFAULT_HUE)),
                "shuffle":self.shuffle,
                "repeat":self.repeat.name.lower(),
                "volume":self.vol.value() if hasattr(self,'vol') else 0,
                "version":APP_VERSION,
                # v16: Browse state for the agent
                "browse": self._browse_get_status() if hasattr(self, "_browse_get_status") else {},
                # v16.8: History + session stats for the agent
                "history": self._get_history_status() if hasattr(self, "_get_history_status") else {},
                "session": self._get_session_status() if hasattr(self, "_get_session_status") else {},
                # v17.0: Equalizer + repeat/skip stats
                "equalizer": self._get_equalizer_status() if hasattr(self, "_get_equalizer_status") else {},
                "repeat_stats": self._get_repeat_stats_status() if hasattr(self, "_get_repeat_stats_status") else {},
                "updated":datetime.now().isoformat()},indent=2))
        except Exception as e: print(f"[Aurora] status write: {e}", flush=True)
    def prev(self):
        # v17.0: record skip-backward (only if we actually skip, not restart)
        if self.player.position() <= 3000:
            try: record_skip("backward")
            except Exception: pass
        if self.player.position()>3000: self.player.setPosition(0)
        elif self.queue and self.qidx>0:  # v15: honor the queue going backwards
            self.qidx-=1; self._play_song(self.queue[self.qidx]); self._refq()
        elif self.cur_idx>0: self.play_idx(self.cur_idx-1)
    def _shuf(self):
        self.shuffle=self.sh.isChecked(); self.cfg["shuffle"]=self.shuffle; save_cfg(self.cfg)
    def _rep(self):
        if self.repeat==RepeatMode.OFF: self.repeat=RepeatMode.ALL; self.rp.setIcon(_svg(IC_REPEAT)); self.rp.setChecked(True)
        elif self.repeat==RepeatMode.ALL: self.repeat=RepeatMode.ONE; self.rp.setIcon(_svg(IC_REPEAT1))
        else: self.repeat=RepeatMode.OFF; self.rp.setIcon(_svg(IC_REPEAT)); self.rp.setChecked(False)
        self.cfg["repeat"]=self.repeat.name.lower(); save_cfg(self.cfg)
    def _pos(self,p):
        # v12.2: don't fight the user while they're dragging the seek handle
        if not self.seek.isSliderDown(): self.seek.setValue(int(p))
        self.ct2.setText(fmt_time(p/1000))
        # v17.5: A-B loop check — if we passed B, jump back to A
        if self._ab_looping and self._ab_a is not None and self._ab_b is not None:
            if p >= self._ab_b:
                self.player.setPosition(self._ab_a)
    def _ab_set(self, point):
        """v17.5: Set A or B loop point at the current playback position."""
        pos = self.player.position()
        if point == "A":
            self._ab_a = pos
            self.ab_a_btn.setChecked(True)
            self.ab_a_btn.setText(f" A\n{fmt_time(pos/1000)}")
            print(f"[Aurora][A-B] A set at {pos}ms ({fmt_time(pos/1000)})", flush=True)
        elif point == "B":
            self._ab_b = pos
            self.ab_b_btn.setChecked(True)
            self.ab_b_btn.setText(f" B\n{fmt_time(pos/1000)}")
            print(f"[Aurora][A-B] B set at {pos}ms ({fmt_time(pos/1000)})", flush=True)
        # If both A and B are set, enable looping
        if self._ab_a is not None and self._ab_b is not None and self._ab_b > self._ab_a:
            self._ab_looping = True
            print(f"[Aurora][A-B] Loop active: {fmt_time(self._ab_a/1000)} → {fmt_time(self._ab_b/1000)}", flush=True)
    def _ab_clear(self):
        """v17.5: Clear A-B loop points."""
        self._ab_a = None; self._ab_b = None; self._ab_looping = False
        self.ab_a_btn.setChecked(False); self.ab_b_btn.setChecked(False)
        self.ab_a_btn.setText(" A"); self.ab_b_btn.setText(" B")
        print("[Aurora][A-B] Loop cleared", flush=True)
    def _dur(self,d): self.seek.setRange(0,int(d)); self.tt.setText(fmt_time(d/1000))
    def _status(self,s):
        if s==QMediaPlayer.EndOfMedia:
            print(f"[Aurora] Track ended. repeat={self.repeat} shuffle={self.shuffle}", flush=True)
            if self.repeat==RepeatMode.ONE:
                self.player.setPosition(0); self.player.play()
            elif self.shuffle and len(self.songs)>1:
                import random
                idx = random.randint(0, len(self.songs)-1)
                if idx == self.cur_idx: idx = (idx + 1) % len(self.songs)
                self.play_idx(idx)
            else:
                self.next()
    # ===== v13: perceptual volume + pop-free fade-in =====
    @staticmethod
    def _curve(v):
        """Slider 0-100 -> perceptual (quadratic~log) gain. Linear volume
        feels 'jumpy/clicky' at the low end on small speakers."""
        return (max(0,min(100,v))/100.0)**2
    def _fade_in(self):
        """~120ms volume ramp after a source swap — kills the switch 'click'."""
        self._fade_step=0
        target=self._curve(self.vol.value())
        if getattr(self,'_fade_timer',None) is None:
            self._fade_timer=QTimer(self); self._fade_timer.setInterval(15)
            self._fade_timer.timeout.connect(self._fade_tick)
        self._fade_target=target
        self._fade_timer.start()
    def _fade_tick(self):
        self._fade_step+=1
        steps=8
        self.audio.setVolume(self._fade_target*self._fade_step/steps)
        if self._fade_step>=steps: self._fade_timer.stop()
    def _vol(self,v):
        if getattr(self,'_fade_timer',None) is not None and self._fade_timer.isActive():
            self._fade_timer.stop()
        self.audio.setVolume(self._curve(v)); self.cfg["vol"]=v; save_cfg(self.cfg)
    def _sortc(self,i): self.sort=SortMode(i); self.cfg["sort"]=self.sort.name.lower(); save_cfg(self.cfg); self._apply_sort(); self._refresh()
    # ===== v15: playlist operations (store = name -> list of file paths) =====
    def _pl_paths(self,name):
        """Normalized list of paths for a playlist (tolerates old dict entries)."""
        out=[]
        for e in self.playlists.get(name,[]):
            if isinstance(e,str): out.append(e)
            elif isinstance(e,dict) and e.get("path"): out.append(e["path"])
        return out
    def _resolve(self,path):
        """Path -> song dict (from library if scanned, else read metadata)."""
        for s in self.songs:
            if s["path"]==path: return s
        fp=Path(path)
        if fp.exists():
            try: return get_metadata(fp)
            except Exception: pass
        return {"title":fp.stem,"artist":"(missing file)","album":"","duration":0,"art":None,"path":path,"date":0}
    def _newpl(self,name=None):
        if not name:
            name,ok=QInputDialog.getText(self,"New Playlist","Playlist name:")
            if not ok: return None
        name=(name or "").strip()
        if not name: return None
        if name not in self.playlists: self.playlists[name]=[]
        save_pl(self.playlists); self._refpl(); self._write_status()
        return name
    def _refpl(self):
        self.pllist.clear()
        for n in self.playlists:
            k=len(self._pl_paths(n))
            it=QListWidgetItem(f"  \u266B  {n}   \u2022   {k} song{'s' if k!=1 else ''}")
            it.setData(Qt.UserRole,n); self.pllist.addItem(it)
    def _pl_ctx(self,pos):
        it=self.pllist.itemAt(pos)
        if not it: return
        name=it.data(Qt.UserRole); m=QMenu()
        for txt,fn in [("Open",lambda:self._open_pl(name)),("Play",lambda:self.play_playlist(name)),
                       ("Add to queue",lambda:self._pl_enqueue(name)),
                       ("Rename",lambda:self._pl_rename(name)),("Delete",lambda:self._pl_delete(name))]:
            a=QAction(txt,self); a.triggered.connect(fn); m.addAction(a)
        m.exec(self.pllist.mapToGlobal(pos))
    def _open_pl(self,name):
        if name not in self.playlists: return
        self._pl_open=name; self._ref_pl_detail(); self.plstack.setCurrentIndex(1)
    def _ref_pl_detail(self):
        name=self._pl_open
        if name is None or name not in self.playlists:
            self.plstack.setCurrentIndex(0); return
        self._pl_songs=[self._resolve(p) for p in self._pl_paths(name)]
        self.pl_title.setText(name)
        total=sum(s["duration"] for s in self._pl_songs)
        self.pl_sub.setText(f"{len(self._pl_songs)} songs  \u2022  {fmt_time(total)}" if self._pl_songs else "Empty playlist — click 'Add Songs'")
        self.pl_songlist.clear()
        for i,_ in enumerate(self._pl_songs):
            it=QListWidgetItem(""); it.setData(Qt.UserRole,i); self.pl_songlist.addItem(it)
    def _pl_add_songs(self):
        """v15: multi-select picker dialog — THE missing 'add song to playlist'."""
        if self._pl_open is None: return
        if not self.songs:
            QInputDialog.getText(self,"Library empty","No songs in ~/Downloads/ yet. OK:"); return
        dlg=QDialog(self); dlg.setWindowTitle(f"Add songs to '{self._pl_open}'")
        dlg.setMinimumSize(460,520)
        dlg.setStyleSheet(f"background:{M3['surface_container_high']}; color:{M3['on_surface']};")
        lay=QVBoxLayout(dlg); lay.setSpacing(10)
        srch=QLineEdit(); srch.setPlaceholderText("Filter songs...")
        srch.setStyleSheet(_m3ss("QLineEdit { background:@surface_container_low; border:1px solid @outline_variant; border-radius:18px; padding:9px 16px; color:@on_surface; }"))
        lay.addWidget(srch)
        lst=QListWidget(); lst.setObjectName("pickerList"); lst.setSelectionMode(QAbstractItemView.MultiSelection)
        have=set(self._pl_paths(self._pl_open))
        def fill():
            tx=srch.text().lower(); lst.clear()
            for s in self.songs:
                if tx and tx not in f"{s['title']} {s['artist']} {s['album']}".lower(): continue
                mark="\u2713 " if s["path"] in have else ""
                it=QListWidgetItem(f"{mark}{s['title']}  \u2014  {s['artist']}")
                it.setData(Qt.UserRole,s["path"]); lst.addItem(it)
        fill(); srch.textChanged.connect(fill)
        lay.addWidget(lst,stretch=1)
        bb=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Add Selected")
        bb.setStyleSheet(_m3ss("QPushButton { background:@primary; color:@on_primary; border-radius:18px; padding:9px 22px; font-weight:500; } QPushButton:hover { background:@primary_hover; }"))
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec()==QDialog.Accepted:
            added=0
            for it in lst.selectedItems():
                p=it.data(Qt.UserRole)
                if p not in have:
                    self.playlists[self._pl_open].append(p); have.add(p); added+=1
            if added:
                save_pl(self.playlists); self._ref_pl_detail(); self._write_status()
    def add_to_playlist(self,name,path):
        """Add one path to a playlist (creates it if needed). Used by UI + agent."""
        if name not in self.playlists: self.playlists[name]=[]
        if path not in self._pl_paths(name):
            self.playlists[name].append(path); save_pl(self.playlists)
        if self._pl_open==name: self._ref_pl_detail()
        self._refpl(); self._write_status()
    def _pl_rename(self,name=None):
        name=name or self._pl_open
        if name is None or name not in self.playlists: return
        new,ok=QInputDialog.getText(self,"Rename Playlist","New name:",text=name)
        new=(new or "").strip()
        if not ok or not new or new==name or new in self.playlists: return
        self.playlists={ (new if k==name else k):v for k,v in self.playlists.items() }
        if self._pl_open==name: self._pl_open=new
        save_pl(self.playlists); self._refpl(); self._ref_pl_detail(); self._write_status()
    def _pl_delete(self,name=None):
        name=name or self._pl_open
        if name is None or name not in self.playlists: return
        del self.playlists[name]; save_pl(self.playlists)
        if self._pl_open==name:
            self._pl_open=None; self.plstack.setCurrentIndex(0)
        self._refpl(); self._write_status()
    def _pl_song_ctx(self,pos):
        it=self.pl_songlist.itemAt(pos)
        if not it: return
        i=it.data(Qt.UserRole); m=QMenu()
        acts=[("Play from here",lambda:self.play_playlist(self._pl_open,i)),
              ("Remove from playlist",lambda:self._pl_remove_song(i)),
              ("Move up",lambda:self._pl_move_song(i,-1)),
              ("Move down",lambda:self._pl_move_song(i,1)),
              ("Add to queue",lambda:(self.queue.append(self._pl_songs[i]),self._refq()))]
        for txt,fn in acts:
            a=QAction(txt,self); a.triggered.connect(fn); m.addAction(a)
        m.exec(self.pl_songlist.mapToGlobal(pos))
    def _pl_remove_song(self,i):
        paths=self._pl_paths(self._pl_open)
        if 0<=i<len(paths):
            paths.pop(i); self.playlists[self._pl_open]=paths
            save_pl(self.playlists); self._ref_pl_detail(); self._write_status()
    def _pl_move_song(self,i,d):
        paths=self._pl_paths(self._pl_open); j=i+d
        if 0<=i<len(paths) and 0<=j<len(paths):
            paths[i],paths[j]=paths[j],paths[i]; self.playlists[self._pl_open]=paths
            save_pl(self.playlists); self._ref_pl_detail()
    def _pl_enqueue(self,name):
        for p in self._pl_paths(name): self.queue.append(self._resolve(p))
        self._refq()
    def play_playlist(self,name,start=0):
        """v15: playlist -> queue -> play. Also the agent's --play-playlist."""
        if not name or name not in self.playlists: return False
        songs=[self._resolve(p) for p in self._pl_paths(name)]
        songs=[s for s in songs if Path(s["path"]).exists()]
        if not songs: return False
        start=max(0,min(start,len(songs)-1))
        self.queue=list(songs); self.qidx=start; self._refq()
        self._play_song(songs[start])
        return True
    def _play_song(self,s):
        """Play a song dict — via library index when scanned, else directly."""
        idx=next((i for i,ss in enumerate(self.songs) if ss["path"]==s["path"]),-1)
        if idx>=0: self.play_idx(idx)
        else: self.play_file(s["path"])
    # ===== v15: queue operations =====
    def _refq(self):
        self.qlist.clear()
        for i,_ in enumerate(self.queue):
            it=QListWidgetItem(""); it.setData(Qt.UserRole,i); self.qlist.addItem(it)
        if hasattr(self,'q_sub'):
            n=len(self.queue)
            self.q_sub.setText(f"{n} track{'s' if n!=1 else ''} \u2014 double-click to jump, right-click or Delete key to remove" if n else "Queue is empty \u2014 right-click songs in the Library to add them")
        self._write_status()
    def _q_jump(self,i):
        if 0<=i<len(self.queue):
            self.qidx=i; self._play_song(self.queue[i]); self._refq()
    def _q_ctx(self,pos):
        it=self.qlist.itemAt(pos)
        if not it: return
        i=it.data(Qt.UserRole); m=QMenu()
        for txt,fn in [("Play now",lambda:self._q_jump(i)),("Remove",lambda:self.q_remove(i)),
                       ("Move up",lambda:self._q_move(-1,i)),("Move down",lambda:self._q_move(1,i)),
                       ("Clear queue",self._q_clear)]:
            a=QAction(txt,self); a.triggered.connect(fn); m.addAction(a)
        m.exec(self.qlist.mapToGlobal(pos))
    def q_remove(self,i):
        """v15: THE missing 'remove from queue'. Keeps qidx pointing at the
        same now-playing entry."""
        if not (0<=i<len(self.queue)): return
        self.queue.pop(i)
        if i<self.qidx: self.qidx-=1
        elif i==self.qidx: self.qidx=min(self.qidx,len(self.queue)-1)
        self.qidx=max(0,self.qidx)
        self._refq()
    def _q_remove_sel(self):
        it=self.qlist.currentItem()
        if it is not None: self.q_remove(it.data(Qt.UserRole))
    def _q_move(self,d,i=None):
        if i is None:
            it=self.qlist.currentItem()
            if it is None: return
            i=it.data(Qt.UserRole)
        j=i+d
        if 0<=i<len(self.queue) and 0<=j<len(self.queue):
            self.queue[i],self.queue[j]=self.queue[j],self.queue[i]
            if self.qidx==i: self.qidx=j
            elif self.qidx==j: self.qidx=i
            self._refq(); self.qlist.setCurrentRow(j)
    def _q_clear(self):
        self.queue=[]; self.qidx=0; self._refq()
    def _q_save_pl(self):
        if not self.queue: return
        name,ok=QInputDialog.getText(self,"Save Queue as Playlist","Playlist name:")
        name=(name or "").strip()
        if not ok or not name: return
        self.playlists[name]=[s["path"] for s in self.queue]
        save_pl(self.playlists); self._refpl(); self._write_status()
    # ===== v15: settings actions =====
    def _hue_changed(self,v):
        self._update_hue_chip()
        # debounce full retheme (regenerating QSS on every pixel is wasteful)
        if not hasattr(self,'_hue_timer'):
            self._hue_timer=QTimer(self); self._hue_timer.setSingleShot(True)
            self._hue_timer.setInterval(120); self._hue_timer.timeout.connect(self._apply_hue)
        self._hue_timer.start()
    def _update_hue_chip(self):
        if hasattr(self,'hue_chip'):
            h=self.hue_slider.value()
            self.hue_chip.setStyleSheet(f"background:{_hsl(h,0.90,84)}; border-radius:18px; border:2px solid rgba(255,255,255,0.25);")
    def _apply_hue(self):
        h=self.hue_slider.value()
        self.cfg["theme_hue"]=h; save_cfg(self.cfg)
        self._retheme(h)
    def _retheme(self,hue):
        """v15: regenerate palette + stylesheet + icons from a hue, live."""
        apply_theme_hue(hue)
        app=QApplication.instance()
        if app: app.setStyleSheet(build_ss())
        # re-tint icons that were baked with explicit colors
        try:
            self._pi=_svg(IC_PLAY,M3["on_primary_container"]); self._ai=_svg(IC_PAUSE,M3["on_primary_container"])
            self.pp.setIcon(self._ai if self.playing else self._pi)
            for b,ic in [(self.sh,IC_SHUFFLE),(self.pb_btn,IC_PREV),(self.nx,IC_NEXT),
                         (self.rp,IC_REPEAT1 if self.repeat==RepeatMode.ONE else IC_REPEAT)]:
                b.setIcon(_svg(ic))
            self.vol_btn.setIcon(_svg(IC_MUTE if self.audio.isMuted() else IC_VOL))
            self.dev_btn.setIcon(_svg(IC_AUDIO_DEVICE))
            self._newpl_btn.setIcon(_svg(IC_PLUS,M3["on_primary"]))
            self._pl_back_btn.setIcon(_svg(IC_BACK))
            self._pl_play_btn.setIcon(_svg(IC_PLAY,M3["on_primary"]))
            self._pl_add_btn.setIcon(_svg(IC_PLAYLIST_ADD,M3["on_secondary_container"]))
            self._pl_ren_btn.setIcon(_svg(IC_EDIT,M3["on_secondary_container"]))
            self._pl_del_btn.setIcon(_svg(IC_TRASH,M3["error"]))
            for b,ic in zip(self._q_btns,[IC_UP,IC_DOWN,IC_CLOSE]): b.setIcon(_svg(ic))
            self._q_save_btn.setIcon(_svg(IC_PLAYLIST_ADD,M3["on_secondary_container"]))
            self._q_clear_btn.setIcon(_svg(IC_TRASH,M3["error"]))
            self._theme_reset_btn.setIcon(_svg(IC_REFRESH,M3["on_secondary_container"]))
            self.viz_btn.setIcon(_svg(IC_CHECK,M3["on_secondary_container"]))
            self._dev_choose_btn.setIcon(_svg(IC_AUDIO_DEVICE,M3["on_secondary_container"]))
            self._theme_icon.setPixmap(_svg(IC_PALETTE,M3["primary"]).pixmap(22,22))
            self._viz_icon.setPixmap(_svg(IC_EQ,M3["primary"]).pixmap(22,22))
            self._dev_icon.setPixmap(_svg(IC_AUDIO_DEVICE,M3["primary"]).pixmap(22,22))
            self._sidebar_title.setStyleSheet(f"font-size:22px;font-weight:500;color:{M3['primary']};padding:24px 20px 4px;background:transparent;")
            # v16: re-tint Browse icons
            if hasattr(self, "browse_btn"):
                self.browse_btn.setIcon(_svg(IC_BROWSE, M3["on_primary_container"]))
            if hasattr(self, "navs") and "browse" in self.navs:
                self.navs["browse"].setIcon(_svg(IC_BROWSE, M3["on_surface_variant"]))
            # v16.8: re-tint History nav icon
            if hasattr(self, "navs") and "history" in self.navs:
                self.navs["history"].setIcon(_svg(IC_HISTORY, M3["on_surface_variant"]))
            # v17.0: re-tint Equalizer nav icon
            if hasattr(self, "navs") and "equalizer" in self.navs:
                self.navs["equalizer"].setIcon(_svg(IC_EQUALIZER, M3["on_surface_variant"]))
        except Exception as e:
            print(f"[Aurora] retheme icon refresh: {e}", flush=True)
        self.backdrop.update()
        for lw in (self.slist,self.qlist,self.pl_songlist): lw.viewport().update()
        self.viz.update()
        # v16: refresh browse cards so they pick up the new palette
        if hasattr(self, "browse_grid"):
            self.browse_grid.parent().update() if self.browse_grid.parent() else None
        self._write_status()
    def _viz_toggle(self):
        on=self.viz_btn.isChecked()
        self.cfg["show_viz"]=on; save_cfg(self.cfg)
        self.viz.setVisible(on)
        self.viz_btn.setText("  Beat graph: ON" if on else "  Beat graph: OFF")
    def _on_viz_mode_changed(self):
        """v17.3: Visualizer mode changed in Settings — save + apply."""
        mode = self.viz_mode_combo.currentIndex()
        cfg = load_viz_config()
        cfg["mode"] = mode
        save_viz_config(cfg)
        # Update the Visualizer widget's mode
        if hasattr(self, "viz"):
            self.viz.viz_mode = mode
            self.viz.update()
        print(f"[Aurora][Viz] mode changed to: {VIZ_MODES[mode]}", flush=True)
    def _on_viz_param_changed(self):
        """v17.3: Visualizer bar width/gap/rounded changed — save + apply."""
        cfg = load_viz_config()
        if hasattr(self, "viz_bar_width_spin"):
            cfg["bar_width"] = self.viz_bar_width_spin.value()
        if hasattr(self, "viz_bar_gap_spin"):
            cfg["bar_gap"] = self.viz_bar_gap_spin.value()
        if hasattr(self, "viz_rounded_chk"):
            cfg["rounded"] = self.viz_rounded_chk.isChecked()
        save_viz_config(cfg)
        if hasattr(self, "viz"):
            self.viz.bar_w = cfg.get("bar_width", 4)
            self.viz.gap = cfg.get("bar_gap", 2)
            self.viz.rounded = cfg.get("rounded", True)
            self.viz.update()
    def _mute_toggle(self):
        m=not self.audio.isMuted(); self.audio.setMuted(m)
        self.vol_btn.setIcon(_svg(IC_MUTE if m else IC_VOL))
        self.vol_btn.setToolTip("Unmute" if m else "Mute")
    def _check_cmd(self):
        f=CONFIG_DIR/"cmd.txt"
        if f.exists():
            try:
                args=f.read_text().strip().split("\n"); f.unlink()
                if args and args[0]:
                    print(f"[Aurora] IPC received: {args[0]}", flush=True)
                    if args[0]=="--play-file" and len(args)>=2: self._on_remote_cmd("play-file",args[1])
                    elif args[0]=="--play": self._on_remote_cmd("play","")
                    elif args[0]=="--pause": self._on_remote_cmd("pause","")
                    elif args[0]=="--toggle": self._on_remote_cmd("toggle","")
                    elif args[0]=="--next": self._on_remote_cmd("next","")
                    elif args[0] in ("--prev","--previous"): self._on_remote_cmd("prev","")
                    elif args[0]=="--stop": self._on_remote_cmd("stop","")
                    # v15: queue / playlist / theme over IPC
                    elif args[0]=="--queue-file" and len(args)>=2: self._on_remote_cmd("queue-file",args[1])
                    elif args[0]=="--queue-next-file" and len(args)>=2: self._on_remote_cmd("queue-next-file",args[1])
                    elif args[0]=="--queue-remove" and len(args)>=2: self._on_remote_cmd("queue-remove",args[1])
                    elif args[0]=="--queue-clear": self._on_remote_cmd("queue-clear","")
                    elif args[0]=="--new-playlist" and len(args)>=2: self._on_remote_cmd("new-playlist",args[1])
                    elif args[0]=="--add-to-playlist" and len(args)>=3: self._on_remote_cmd("add-to-playlist",args[1]+"\n"+args[2])
                    elif args[0]=="--play-playlist" and len(args)>=2: self._on_remote_cmd("play-playlist",args[1])
                    elif args[0]=="--set-theme" and len(args)>=2: self._on_remote_cmd("set-theme",args[1])
                    # v16/v16.5: Browse IPC
                    elif args[0]=="--browse-search" and len(args)>=2: self._on_remote_cmd("browse-search",args[1])
                    elif args[0]=="--browse-country" and len(args)>=2: self._on_remote_cmd("browse-country",args[1])
                    elif args[0]=="--browse-preview" and len(args)>=2: self._on_remote_cmd("browse-preview",args[1])  # v16.5: deprecated
                    elif args[0]=="--browse-load-more": self._on_remote_cmd("browse-load-more","")
                    elif args[0]=="--browse-download" and len(args)>=2: self._on_remote_cmd("browse-download",args[1])
            except Exception as e: print(f"[Aurora] IPC error: {e}", flush=True)

    # ===== v12.3: audio output device selector =====
    def _show_device_selector(self):
        """Show dialog with available audio output devices."""
        devices = QMediaDevices.audioOutputs()
        if not devices:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Select Audio Output")
        dlg.setMinimumWidth(300)
        # M3 dialog: surface-container-high, list items with state layers
        dlg.setStyleSheet(f"background:{M3['surface_container_high']}; color:{M3['on_surface']};")
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        lst.setStyleSheet(_m3ss("""
            QListWidget { background:@surface_container; border:1px solid @outline_variant; border-radius:12px; }
            QListWidget::item { padding:12px 16px; border-radius:8px; margin:2px; }
            QListWidget::item:hover { background:@state_hover_on_surface; }
            QListWidget::item:selected { background:@secondary_container; color:@on_secondary_container; }
        """))
        current_device = self.audio.device()
        for i, dev in enumerate(devices):
            name = dev.description() or f"Device {i+1}"
            item = QListWidgetItem(f"\U0001F50A  {name}")
            item.setData(Qt.UserRole, dev)
            lst.addItem(item)
            if not current_device.isNull() and bytes(dev.id()) == bytes(current_device.id()):
                item.setText("\u2705  " + name)
                lst.setCurrentItem(item)
        lay.addWidget(lst)
        test_btn = QPushButton("Test Selected Device")
        test_btn.setStyleSheet(_m3ss("""
            QPushButton { background:@primary; color:@on_primary; border-radius:20px; padding:10px 24px; font-weight:500; }
            QPushButton:hover { background:@primary_hover; }
        """))  # M3 filled button
        test_btn.clicked.connect(lambda: self._test_device(lst.currentItem()))
        lay.addWidget(test_btn)
        ok_btn = QPushButton("Select")
        ok_btn.setStyleSheet(_m3ss("""
            QPushButton { background:@secondary_container; color:@on_secondary_container; border-radius:20px; padding:10px 24px; font-weight:500; }
            QPushButton:hover { background:@secondary_container_hover; }
        """))  # M3 filled tonal button
        ok_btn.clicked.connect(lambda: self._apply_device_selection(lst.currentItem(), dlg))
        lay.addWidget(ok_btn)
        dlg.exec()

    def _apply_device_selection(self, item, dlg):
        if not item:
            return
        dev = item.data(Qt.UserRole)
        if dev and not dev.isNull():
            self.audio.setDevice(dev)
            import base64
            self.cfg["audio_device_id"] = base64.b64encode(bytes(dev.id())).decode()
            save_cfg(self.cfg)
            self._write_status()
        dlg.accept()

    def _test_device(self, item):
        """Play a 3-second test tone on the selected device."""
        if not item:
            return
        dev = item.data(Qt.UserRole)
        if not dev or dev.isNull():
            return
        # Stop any previous test still playing (rapid re-clicks)
        if self._test_player is not None:
            try: self._test_player.stop()
            except Exception: pass
        import tempfile, wave, struct, math
        sample_rate, duration, freq = 44100, 3.0, 440.0
        samples = int(sample_rate * duration)
        frames = b''.join(
            struct.pack('<h', int(32767 * 0.3 * math.sin(2 * math.pi * freq * i / sample_rate)))
            for i in range(samples))
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            test_file = f.name
        w = wave.open(test_file, 'wb')
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate)
        w.writeframes(frames); w.close()
        # Separate player so main playback + MPRIS state is untouched
        test_audio = QAudioOutput()
        test_audio.setDevice(dev)
        test_audio.setVolume(0.5)
        test_player = QMediaPlayer()
        test_player.setAudioOutput(test_audio)
        test_player.setSource(QUrl.fromLocalFile(test_file))
        self._test_player = test_player  # keep reference so GC can't kill it mid-tone
        test_player.play()
        def cleanup():
            test_player.stop()
            test_player.deleteLater()
            test_audio.deleteLater()
            if self._test_player is test_player:
                self._test_player = None
            try: os.unlink(test_file)
            except OSError: pass
        QTimer.singleShot(3200, cleanup)

    def _on_audio_devices_changed(self):
        """Called when a device connects/disconnects (e.g. Bluetooth)."""
        saved_device_id = self.cfg.get("audio_device_id")
        if not saved_device_id:
            return
        import base64
        try:
            target_id = base64.b64decode(saved_device_id)
        except Exception:
            return
        for d in QMediaDevices.audioOutputs():
            if bytes(d.id()) == target_id:
                self.audio.setDevice(d)  # auto-switch back when preferred device returns
                break

    def _save_session_time(self):
        """v16.8: Periodically save session time so total_app_seconds accumulates
        even if the app crashes (doesn't reach closeEvent)."""
        try:
            if not hasattr(self, "_session"): return
            started = datetime.fromisoformat(self._session.get("session_started", datetime.now().isoformat()))
            session_seconds = (datetime.now() - started).total_seconds()
            self._session["total_app_seconds"] = self._session.get("total_app_seconds", 0) + session_seconds
            self._session["session_started"] = datetime.now().isoformat()  # reset for next interval
            save_session(self._session)
        except Exception as e:
            print(f"[Aurora][Session] save failed: {e}", flush=True)

    def closeEvent(self,e):
        self.cfg["w"]=self.width(); self.cfg["h"]=self.height(); save_cfg(self.cfg); save_pl(self.playlists)
        # v16.8: save final session time on exit
        self._save_session_time()
        e.accept()

# ===== IPC =====
def is_running():
    if PID_FILE.exists():
        try:
            old=int(PID_FILE.read_text().strip()); os.kill(old,0)
            # Verify the PID actually belongs to Aurora (PID reuse guard).
            # Without this, if Aurora crashed and the PID was reused by some
            # other process, send_cmd() would silently no-op and the agent's
            # song would never play.
            try:
                cmdline = Path(f"/proc/{old}/cmdline").read_text(errors="replace")
                if "aurora_player" in cmdline:
                    return True
                # PID reused by another process — clean up stale lock
                PID_FILE.unlink(missing_ok=True)
                return False
            except (FileNotFoundError, OSError):
                # /proc not available (non-Linux) — trust os.kill result
                return True
        except: PID_FILE.unlink(missing_ok=True)
    return False

def send_cmd(args):
    (CONFIG_DIR/"cmd.txt").write_text("\n".join(args))

# ===== v16.8: /helper command — comprehensive command reference =====
def _print_helper_command():
    """v16.8: Print ALL available commands grouped by category. This is the
    agent's one-stop reference when running in a CLI/terminal. Triggered by
    `aurora-player /helper` or `aurora-player --helper`."""
    print(f"""
╔══════════════════════════════════════════════════════════════════════════╗
║                    {APP_NAME} v{APP_VERSION} — /helper                       ║
║              Complete command reference for agents & CLI                  ║
╚══════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 LAUNCH & META
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  aurora-player                              Launch GUI (single-instance)
  aurora-player --version / -v               Print version
  aurora-player --help / -h                  Short help
  aurora-player /helper  (or --helper)       THIS full command reference (v16.8)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PLAYBACK CONTROL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  aurora-player --play-file <path>           Play a file from ~/Downloads/
  aurora-player --play                       Play (resume)
  aurora-player --pause                      Pause
  aurora-player --toggle                     Play/pause toggle
  aurora-player --next                       Next track
  aurora-player --prev / --previous          Previous track
  aurora-player --stop                       Stop playback
  playerctl --player=aurora play/pause/stop/next/previous   MPRIS control

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 QUEUE (v15)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  aurora-player --queue-file <path>          Add file to end of queue
  aurora-player --queue-next-file <path>     Add file right after current track
  aurora-player --queue-remove <n>           Remove queue entry n (1-based)
  aurora-player --queue-clear                Empty the queue

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PLAYLISTS (v15)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  aurora-player --list-playlists             JSON: name -> song count
  aurora-player --new-playlist <name>        Create playlist (works offline too)
  aurora-player --add-to-playlist <name> <path>
                                              Add file to playlist
  aurora-player --play-playlist <name>       Load playlist into queue and play

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 THEME (v15)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  aurora-player --set-theme <hue 0-359>      Retheme whole app from a hue
                                             (239 = default Aurora indigo)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 BROWSE — iTunes search + infinite scroll + FULL-TRACK download (v16/v16.5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  aurora-player --browse-search <query>              Run search in GUI (first page)
  aurora-player --browse-country <US|IN|GB|CA|AU|DE|FR|JP>
                                                      Change iTunes storefront
                                                      (v16.7: country-specific seeds)
  aurora-player --browse-load-more                   Load next page (infinite scroll)
  aurora-player --browse-download <trackId>          Full-track download (6-strategy
                                                      bot-bypass) -> ~/Downloads/
  aurora-player --browse-itunes <query> [country] [offset]
                                                      Headless search (JSON to stdout,
                                                      paginated)
  NOTE: --browse-preview is DEPRECATED in v16.5 (preview button removed).
  v16.7: double-click any Browse card to play (downloads first if needed).
  v16.7: country change auto-loads country-specific seed (IN=Bollywood, US=pop).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 YOUTUBE AUTH — bot-protection bypass (v16.6)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  aurora-player --browse-auth-status                 Print auth config (JSON)
  Strategies (tried in order until one works):
    1. cookies-from-browser  (--cookies-from-browser <browser>)
    2. cookies-file          (--cookies <cookies.txt>)
    3. client-rotation       (--extractor-args youtube:player_client=ios,android,tv,web,web_safari)
    4. invidious             (3 instances: vid.puffyan.us, invidious.perennialte.ch, yewtu.be)
    5. innertube             (SAPISIDHASH + 5 client types: iOS=5, Android=3, TV=7, WEB=1, WEB_REMIX=67)
    6. plain-ytdlp           (last resort, no auth)
  Configure in: Settings → YouTube Auth card (strategy dropdown, browser picker,
  cookies.txt file picker, SAPISID cookie string field).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 HISTORY (v16.8 NEW)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  aurora-player --history                              Print history JSON (last 100 songs)
  aurora-player --history-clear                        Clear all history entries
  aurora-player --history-stats                        Print session + total-time stats
  Tracks per song: title, artist, path, first_played, last_played, play_count
  Session stats: session_started, session_seconds, total_app_seconds (cumulative)
  Files: ~/.aurora-player/history.json + ~/.aurora-player/session.json
  Max 100 entries (FIFO eviction; evicted play_counts preserved in aggregate stats).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 STATUS & INFO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  aurora-player --status                     JSON playback state (incl. queue,
                                             playlists, theme, browse, history, session)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 KEYBOARD SHORTCUTS (in GUI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Space                 Play/Pause toggle
  → (Right arrow)       Next track
  ← (Left arrow)        Previous track
  ↑ (Up arrow)          Volume +5
  ↓ (Down arrow)        Volume -5
  Ctrl+F                Focus search bar (Library page)
  Esc                   Stop playback
  F5                    Context-aware refresh (v16.7):
                          • Library page → rescan ~/Downloads/
                          • Browse page → re-fire current search
  Delete                Remove selected queue row (when Queue page focused)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 MOUSE / GESTURES (in GUI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Double-click song (Library)         Play song
  Double-click playlist               Open playlist detail page
  Double-click queue row              Jump-play that queue entry
  Double-click Browse card (v16.7)    Play song (downloads first if needed)
  Right-click song (Library)          Context menu: Play, Add to queue, Add to playlist
  Right-click history entry (v16.8)   Context menu: Play, Show details, Remove
  Click beat graph (Settings: ON)     Seek to that position
  Drag beat graph                     Scrub through track

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SIDEBAR PAGES (v16.8)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Library     — ~/Downloads/ auto-scan, search, sort, MPRIS control
  Browse      — iTunes Search API, infinite scroll, full-track download (v16/v16.5)
  History     — Last 100 played songs + session/total-time stats (v16.8 NEW)
  Playlists   — Create/rename/delete, add songs, play
  Queue       — Up next, reorder, save as playlist
  Settings    — Theme color slider, beat graph toggle, audio device, YouTube Auth

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 FILE PATHS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Music library:    ~/Downloads/ (auto-scanned every 10 min, F5 to refresh)
  Config:           ~/.aurora-player/settings.json
  Playlists:        ~/.aurora-player/playlists.json
  Status JSON:      ~/.aurora-player/status.json
  History (v16.8):  ~/.aurora-player/history.json
  Session (v16.8):  ~/.aurora-player/session.json
  PID lock:         ~/.aurora-player/pid.lock
  IPC command file: ~/.aurora-player/cmd.txt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 INSTALLATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  From zip:    bash aurora-player/install.sh
  From .deb:   sudo apt install ./packages/aurora-music_{APP_VERSION}_all.deb
  Dependencies: PySide6, mpris_server, mutagen, yt-dlp, ffmpeg
  Python deps:  pip install --break-system-packages PySide6 mpris_server mutagen yt-dlp
  System deps:  sudo apt install ffmpeg

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 VERSION HISTORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  v16.8 — History page (100 songs, play count, session time) + /helper command
  v16.7 — Double-click to play + search race-condition fix + country-specific seeds
  v16.6 — Multi-strategy YouTube bot-protection bypass (6 strategies)
  v16.5 — Infinite scroll + preview button removed + full-track downloads
  v16.0 — Browse feature (iTunes Search API + 1-click download)
  v15.0 — Playlists + Queue + Theme Studio + Beat Graph
  v14.0 — Material 3 Redesign
  v12.x — MPRIS, single-instance IPC, agent CLI

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
* TIP: Run `aurora-player /helper` anytime to see this reference.
   Pipe to `less` for pagination: `aurora-player /helper | less`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

# ===== Main =====
def main():
    args=sys.argv[1:]
    if args and args[0] in ("--play","--pause","--toggle","--next","--prev","--previous","--stop","--queue-clear"):
        if is_running(): send_cmd(args); print(f"[Aurora] Sent: {args[0]}"); return
        else: print("[Aurora] Not running."); sys.exit(1)
    # ===== v15: playlist / queue / theme CLI for the agent =====
    if args and args[0]=="--list-playlists":
        pls=load_pl()
        print(json.dumps({n:len(v) for n,v in pls.items()},indent=2)); return
    if args and args[0]=="--new-playlist":
        if len(args)<2: print("Usage: aurora-player --new-playlist <name>"); sys.exit(1)
        if is_running(): send_cmd(args[:2]); print(f"[Aurora] Sent: new playlist '{args[1]}'"); return
        pls=load_pl(); pls.setdefault(args[1],[]); save_pl(pls)
        print(f"[Aurora] Created playlist '{args[1]}' (offline)."); return
    if args and args[0]=="--add-to-playlist":
        if len(args)<3: print("Usage: aurora-player --add-to-playlist <playlist> <file>"); sys.exit(1)
        if is_running(): send_cmd(args[:3]); print(f"[Aurora] Sent: add to '{args[1]}'"); return
        pls=load_pl(); pls.setdefault(args[1],[])
        if args[2] not in pls[args[1]]: pls[args[1]].append(args[2])
        save_pl(pls); print(f"[Aurora] Added to '{args[1]}' (offline)."); return
    if args and args[0]=="--set-theme":
        if len(args)<2: print("Usage: aurora-player --set-theme <hue 0-359>"); sys.exit(1)
        if is_running(): send_cmd(args[:2]); print(f"[Aurora] Sent: theme hue {args[1]}"); return
        c=load_cfg(); c["theme_hue"]=int(args[1])%360; save_cfg(c)
        print(f"[Aurora] Theme hue {int(args[1])%360} saved (applies on next launch)."); return
    if args and args[0] in ("--play-playlist","--queue-file","--queue-next-file","--queue-remove"):
        if len(args)<2: print(f"Usage: aurora-player {args[0]} <arg>"); sys.exit(1)
        if is_running(): send_cmd(args[:2]); print(f"[Aurora] Sent: {args[0]} {args[1]}"); return
        else: print("[Aurora] Not running. Launch aurora-player first."); sys.exit(1)
    # ===== v16: Browse CLI for the agent =====
    if args and args[0]=="--browse-search":
        if len(args)<2: print("Usage: aurora-player --browse-search <query>"); sys.exit(1)
        if is_running(): send_cmd(args[:2]); print(f"[Aurora] Sent: browse-search '{args[1]}'"); return
        else: print("[Aurora] Not running. Launch aurora-player first, then send --browse-search."); sys.exit(1)
    if args and args[0]=="--browse-country":
        if len(args)<2: print("Usage: aurora-player --browse-country <US|IN|GB|CA|AU|DE|FR|JP>"); sys.exit(1)
        if is_running(): send_cmd(args[:2]); print(f"[Aurora] Sent: browse-country {args[1]}"); return
        else: print("[Aurora] Not running."); sys.exit(1)
    if args and args[0]=="--browse-load-more":
        # v16.5: trigger the next page of results via IPC (infinite scroll from agent)
        if is_running(): send_cmd(["--browse-load-more"]); print("[Aurora] Sent: browse-load-more"); return
        else: print("[Aurora] Not running."); sys.exit(1)
    if args and args[0]=="--browse-preview":
        # v16.5: deprecated — preview button removed. Print a hint and exit.
        print("[Aurora] --browse-preview is deprecated in v16.5 (preview button removed).")
        print("         Use --browse-download for full-track download (yt-dlp + ffmpeg).")
        sys.exit(0)
    # v16.6: --browse-auth-status prints the current YouTube auth config as JSON
    if args and args[0]=="--browse-auth-status":
        c = load_cfg()
        print(json.dumps({
            "version": APP_VERSION,
            "yt_auth_strategy":  c.get("yt_auth_strategy",  "auto"),
            "yt_browser_choice": c.get("yt_browser_choice", "firefox"),
            "yt_cookies_file":   c.get("yt_cookies_file",   ""),
            "yt_cookies_file_exists": bool(c.get("yt_cookies_file") and Path(c["yt_cookies_file"]).exists()),
            "yt_cookies_str_set": bool(c.get("yt_cookies_str", "")),
            "strategies_available": [
                "cookies-from-browser", "cookies-file", "client-rotation",
                "invidious", "innertube", "plain-ytdlp",
            ],
            "invidious_instances": INVIDIOUS_INSTANCES,
            "innertube_client_types": [c[0] for c in INNERTUBE_CLIENTS],
        }, indent=2))
        return
    # v16.8: --history prints the last 100 played songs as JSON
    if args and args[0]=="--history":
        h = load_history()
        print(json.dumps({
            "version": APP_VERSION,
            "entries_count": len(h.get("entries", [])),
            "max_entries": HISTORY_MAX_ENTRIES,
            "entries": h.get("entries", []),
            "evicted_play_counts": h.get("play_counts", {}),
            "unique_songs_total": len(h.get("entries", [])) + len(h.get("play_counts", {})),
            "total_plays": sum(e.get("play_count", 0) for e in h.get("entries", [])) + sum(h.get("play_counts", {}).values()),
        }, indent=2))
        return
    # v16.8: --history-clear clears all history entries
    if args and args[0]=="--history-clear":
        h = load_history()
        n = len(h.get("entries", []))
        h["entries"] = []
        # Keep play_counts + total_app_seconds (cumulative stats)
        save_history(h)
        print(f"[Aurora] Cleared {n} history entries (cumulative stats preserved).")
        return
    # v16.8: --history-stats prints session + total-time stats as JSON
    if args and args[0]=="--history-stats":
        sess = load_session()
        try:
            started = datetime.fromisoformat(sess.get("session_started", datetime.now().isoformat()))
            session_seconds = (datetime.now() - started).total_seconds()
        except Exception:
            session_seconds = 0
        total_seconds = sess.get("total_app_seconds", 0) + session_seconds
        h = load_history()
        print(json.dumps({
            "version": APP_VERSION,
            "session_started": sess.get("session_started", ""),
            "session_seconds": int(session_seconds),
            "session_human": fmt_duration(session_seconds),
            "total_app_seconds": int(total_seconds),
            "total_app_human": fmt_duration(total_seconds),
            "unique_songs_played": len(h.get("entries", [])) + len(h.get("play_counts", {})),
            "total_plays": sum(e.get("play_count", 0) for e in h.get("entries", [])) + sum(h.get("play_counts", {}).values()),
            "history_entries": len(h.get("entries", [])),
            "max_history_entries": HISTORY_MAX_ENTRIES,
        }, indent=2))
        return
    if args and args[0]=="--browse-download":
        if len(args)<2: print("Usage: aurora-player --browse-download <trackId>"); sys.exit(1)
        if is_running(): send_cmd(args[:2]); print(f"[Aurora] Sent: browse-download {args[1]}"); return
        else: print("[Aurora] Not running."); sys.exit(1)
    if args and args[0]=="--browse-itunes":
        # v16.5: Headless iTunes search (does NOT need Aurora running) — agent
        # can search, pick a trackId, then send --browse-download to the GUI.
        # Supports --offset N for pagination (infinite scroll from headless agents).
        if len(args)<2: print("Usage: aurora-player --browse-itunes <query> [country] [offset]"); sys.exit(1)
        q = args[1]
        country = args[2] if len(args)>=3 and len(args[2])==2 else "US"
        try: offset = int(args[3]) if len(args)>=4 else 0
        except ValueError: offset = 0
        limit = min(BROWSE_RESULT_LIMIT, BROWSE_MAX_TOTAL_RESULTS - offset)
        if limit <= 0:
            print(json.dumps({"query": q, "country": country, "offset": offset,
                              "count": 0, "results": [], "has_more": False}, indent=2)); return
        data = _itunes_get(ITUNES_SEARCH_URL, {
            "term": q, "media": ITUNES_MEDIA, "entity": ITUNES_ENTITY,
            "limit": limit, "country": country, "offset": offset,
        })
        results = data.get("results", []) if data else []
        out = []
        for r in results:
            if not r.get("trackName"): continue  # v16.5: previewUrl optional now
            out.append({
                "track_id": str(r.get("trackId","")),
                "title": r.get("trackName",""),
                "artist": r.get("artistName",""),
                "album": r.get("collectionName",""),
                "genre": r.get("primaryGenreName",""),
                "duration_ms": int(r.get("trackTimeMillis") or 0),
                "artwork_url": (r.get("artworkUrl100") or "").replace("100x100bb","300x300bb"),
                "track_url": r.get("trackViewUrl",""),
            })
        has_more = (len(results) >= limit) and (offset + len(results) < BROWSE_MAX_TOTAL_RESULTS)
        print(json.dumps({"query": q, "country": country, "offset": offset,
                          "count": len(out), "has_more": has_more,
                          "results": out}, indent=2))
        return
    if args and args[0]=="--status":
        # v12.2: agent-friendly status without needing playerctl
        if is_running() and STATUS_FILE.exists(): print(STATUS_FILE.read_text()); return
        print('{"state": "not-running"}'); sys.exit(1)
    if args and args[0]=="--play-file":
        if len(args)<2: print("Usage: aurora-player --play-file <path>"); sys.exit(1)
        if is_running(): send_cmd(args); print(f"[Aurora] Sent: {args[1]}"); return
    if args and args[0] in ("--version","-v"): print(f"{APP_NAME} v{APP_VERSION}"); return
    # v16.8: /helper command — print ALL available commands grouped by category.
    # This is the agent's one-stop reference. Triggered by `/helper` or `--helper`.
    if args and args[0] in ("/helper", "--helper"):
        _print_helper_command(); return
    if args and args[0] in ("--help","-h"):
        print(f"""{APP_NAME} v{APP_VERSION}

Usage:
  aurora-player                              Launch GUI
  aurora-player --play-file <path>           Play file
  aurora-player --play/--pause/--toggle/--next/--prev/--stop
  aurora-player --status                     Playback status JSON (incl. queue, playlists, theme, browse)

Queue (v15):
  aurora-player --queue-file <path>          Add file to end of queue
  aurora-player --queue-next-file <path>     Add file right after current track
  aurora-player --queue-remove <n>           Remove queue entry n (1-based)
  aurora-player --queue-clear                Empty the queue

Playlists (v15):
  aurora-player --list-playlists             JSON: name -> song count
  aurora-player --new-playlist <name>        Create playlist (works offline too)
  aurora-player --add-to-playlist <name> <path>
  aurora-player --play-playlist <name>       Load playlist into queue and play

Theme (v15):
  aurora-player --set-theme <hue 0-359>      Retheme whole app from a hue (239 = default indigo)

Browse (v16/v16.5/v16.6) — iTunes search + infinite scroll + FULL-TRACK download + bot-bypass:
  aurora-player --browse-search <query>              Run search in the GUI (first page)
  aurora-player --browse-country <US|IN|GB|CA|...>   Change iTunes storefront
  aurora-player --browse-load-more                   Load next page of results (infinite scroll)
  aurora-player --browse-download <trackId>          Full-track download (6-strategy bot-bypass) -> ~/Downloads/
  aurora-player --browse-itunes <query> [country] [offset]   Headless search (JSON to stdout, paginated)
  aurora-player --browse-auth-status                 v16.6: Print YouTube auth config (JSON)
  NOTE: --browse-preview is DEPRECATED in v16.5 (preview button removed).
  v16.6: --browse-download tries 6 strategies in order:
         cookies-from-browser -> cookies.txt -> client-rotation ->
         Invidious (3 instances) -> SAPISIDHASH Innertube (5 client types) -> plain yt-dlp

History (v16.8 NEW):
  aurora-player --history                            Print history JSON (last 100 songs)
  aurora-player --history-clear                      Clear all history entries
  aurora-player --history-stats                      Print session + total-time stats (JSON)

v16.8: /helper command (alias --helper) prints ALL commands grouped by category.

  playerctl --player=aurora play/pause/play-pause/stop/next/previous

Music: {MUSIC_FOLDER} (auto-scanned)
Config: {CONFIG_FILE}"""); return
    # v12.2: enforce the single-instance lock for plain GUI launches too.
    # Previously a second 'aurora-player' clobbered the PID file, and the two
    # instances fought over IPC — agent commands went to the wrong window.
    if is_running() and not args:
        print("[Aurora] Already running."); return
    PID_FILE.write_text(str(os.getpid()))
    # v15: apply the saved theme hue BEFORE any widget/stylesheet is built
    apply_theme_hue(load_cfg().get("theme_hue",DEFAULT_HUE))
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setApplicationVersion(APP_VERSION); app.setStyleSheet(build_ss())
    w=Win(); w.show()
    if args and args[0]=="--play-file" and len(args)>=2:
        def dp():
            if hasattr(w,'sc') and w.sc.isRunning():
                QTimer.singleShot(500,dp)
                return
            print(f"[Aurora] dp() called, playing: {args[1]}", flush=True)
            w.play_file(args[1])
            # Verify playback started - retry up to 10 times with reload fallback
            retry_count = [0]
            def check_playing():
                state = w.player.playbackState()
                print(f"[Aurora] check_playing: state={state}, retry={retry_count[0]}", flush=True)
                if state != QMediaPlayer.PlayingState and retry_count[0] < 10:
                    w.player.play()
                    retry_count[0] += 1
                    QTimer.singleShot(1000, check_playing)
                elif state == QMediaPlayer.PlayingState:
                    print(f"[Aurora] Playback confirmed!", flush=True)
                else:
                    # Final attempt: reload the source from scratch
                    print(f"[Aurora] Playback failed after {retry_count[0]} retries, reloading source...", flush=True)
                    if w.cur:
                        w.player.setSource(QUrl.fromLocalFile(w.cur["path"]))
                        w.player.play()
            QTimer.singleShot(2000, check_playing)
        QTimer.singleShot(1500,dp)
    def cleanup():
        # v12.2: only remove the lock if WE own it (don't kill another instance's lock)
        try:
            if PID_FILE.exists() and PID_FILE.read_text().strip()==str(os.getpid()): PID_FILE.unlink()
        except: pass
        (CONFIG_DIR/"cmd.txt").unlink(missing_ok=True)
        STATUS_FILE.unlink(missing_ok=True)
    app.aboutToQuit.connect(cleanup)
    sys.exit(app.exec())

if __name__=="__main__": main()

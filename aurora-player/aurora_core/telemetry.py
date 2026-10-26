"""Versioned JSON status construction for humans and autonomous agents."""

from datetime import datetime
from typing import Any, Dict, Iterable, Mapping, Optional


def _track_value(track: Optional[Mapping[str, Any]], key: str, default: Any = "") -> Any:
    return (track or {}).get(key, default)


def build_status(
    *,
    state: str = "stopped",
    track: Optional[Mapping[str, Any]] = None,
    position_ms: int = 0,
    queue: Optional[Iterable[Mapping[str, Any]]] = None,
    queue_index: int = -1,
    volume: float = 0.0,
    eq: Optional[Mapping[str, Any]] = None,
    buffer_health: float = 0.0,
    bitrate: int = 0,
    version: str = "22.0.0",
    theme_hue: int = 239,
    theme_mode: str = "dark",
    repeat: str = "off",
    shuffle: bool = False,
    playlists: Optional[Mapping[str, int]] = None,
    lyrics: Optional[Mapping[str, Any]] = None,
    stream: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    current = dict(track or {})
    duration_ms = int(current.get("duration_ms") or int(current.get("duration") or 0) * 1000)
    bitrate_kbps = int(round(int(bitrate or current.get("bit_rate") or 0) / 1000.0))
    queue_items = [dict(item) for item in (queue or [])]
    queue_position = queue_index + 1 if 0 <= queue_index < len(queue_items) else 0
    eq_data = dict(eq or {})
    eq_data.setdefault("enabled", False)
    eq_data.setdefault("preset", "Flat")
    eq_data.setdefault("gains", [0] * 10)
    volume_value = float(volume)
    volume_percent = int(round(volume_value * 100 if volume_value <= 1 else volume_value))
    status: Dict[str, Any] = {
        "version": version,
        "api_version": 2,
        "state": state,
        "playback_state": state,
        "title": _track_value(track, "title"),
        "artist": _track_value(track, "artist"),
        "path": _track_value(track, "path"),
        "position_ms": max(0, int(position_ms)),
        "position_sec": max(0, int(position_ms) // 1000),
        "duration_ms": duration_ms,
        "duration_sec": duration_ms // 1000,
        "bit_rate_kbps": bitrate_kbps,
        "buffer_health": max(0.0, min(1.0, float(buffer_health))),
        "queue": queue_items[:100],
        "queue_index": queue_index if queue_items else -1,
        "queue_position": queue_position,
        "queue_length": len(queue_items),
        "playlists": dict(playlists or {}),
        "theme_hue": int(theme_hue) % 360,
        "theme_mode": theme_mode,
        "shuffle": bool(shuffle),
        "repeat": repeat,
        "volume": max(0, min(100, volume_percent)),
        "eq_preset": eq_data.get("preset", "Flat"),
        "equalizer": eq_data,
        "current_track": {
            "title": _track_value(track, "title"),
            "artist": _track_value(track, "artist"),
            "album": _track_value(track, "album"),
            "path": _track_value(track, "path"),
            "duration_ms": duration_ms,
            "bit_rate_kbps": bitrate_kbps,
            "has_cover": bool(_track_value(track, "art") or _track_value(track, "has_cover")),
        },
        "updated": datetime.now().isoformat(),
    }
    if lyrics is not None:
        status["lyrics"] = dict(lyrics)
    if stream is not None:
        status["stream"] = dict(stream)
    return status

"""Lyrics parsing and embedded-tag helpers."""

import re
from typing import Any, Dict, List, Optional, Tuple


LyricLine = Tuple[int, str]
_LRC_TIME_RE = re.compile(r"\[(\d+):([0-5]?\d)(?:[.:](\d{1,3}))?\]")


def parse_lrc(lrc_text: str) -> List[LyricLine]:
    """Parse LRC timestamps, including multiple timestamps on one line."""

    if not lrc_text:
        return []
    lines: List[LyricLine] = []
    for raw_line in lrc_text.splitlines():
        matches = list(_LRC_TIME_RE.finditer(raw_line))
        if not matches:
            continue
        text = raw_line[matches[-1].end() :].strip()
        for match in matches:
            minutes, seconds, fraction = match.groups()
            milliseconds = int((fraction or "0").ljust(3, "0")[:3])
            lines.append((int(minutes) * 60000 + int(seconds) * 1000 + milliseconds, text))
    return sorted(lines, key=lambda line: line[0])


def plain_lyrics(text: str, line_interval_ms: int = 5000) -> List[LyricLine]:
    """Turn unsynchronised lyrics into predictable display lines."""

    result: List[LyricLine] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            result.append((len(result) * line_interval_ms, line))
    return result


def parse_embedded_lyrics(text: str) -> Dict[str, Any]:
    """Normalize USLT/plain tag content for the overlay and status contract."""

    synced = parse_lrc(text)
    if synced:
        return {"lines": synced, "source": "embedded-uslt", "synced": True}
    return {
        "lines": plain_lyrics(text),
        "source": "embedded-uslt",
        "synced": False,
    }


def _value_text(value: Any) -> str:
    if hasattr(value, "text"):
        value = value.text
    if isinstance(value, (list, tuple)):
        return "\n".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def read_embedded_lyrics(path: str) -> Optional[Dict[str, Any]]:
    """Read USLT/lyrics tags with mutagen when it is available.

    This helper deliberately returns ``None`` for unavailable or malformed
    files so online lookup can remain the fallback path.
    """

    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path)
        tags = getattr(audio, "tags", None) if audio is not None else None
        if not tags:
            return None
        candidates: List[str] = []
        for key, value in tags.items():
            key_text = str(key).lower()
            if key_text.startswith("uslt") or key_text in {
                "lyrics",
                "unsyncedlyrics",
                "\xa9lyr",
                "lyricist",
            }:
                text = _value_text(value).strip()
                if text:
                    candidates.append(text)
        if not candidates:
            return None
        return parse_embedded_lyrics(candidates[0])
    except Exception:
        return None

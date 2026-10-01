import sys
import os
import json
import tempfile
from pathlib import Path
import pytest

def atomic_write_json(filepath, data, indent=2):
    """Safely write data to JSON file atomically to prevent corruption on crash."""
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        tmp_path.replace(path)
    except Exception as e:
        print(f"[Aurora] atomic_write_json failed for {filepath}: {e}", flush=True)

def fmt_duration(seconds):
    """v16.8: Format seconds into human-readable duration."""
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

def fmt_time(s):
    s = max(0, int(s))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0: return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"

def test_fmt_duration():
    assert fmt_duration(0) == "0s"
    assert fmt_duration(90) == "1m 30s"
    assert fmt_duration(3725) == "1h 2m 5s"
    assert fmt_duration(86400) == "1d 0h 0m"

def test_fmt_time():
    assert fmt_time(0) == "0:00"
    assert fmt_time(65) == "1:05"
    assert fmt_time(3665) == "1:01:05"

def test_atomic_write_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = Path(tmpdir) / "test_data.json"
        data = {"key": "value", "numbers": [1, 2, 3], "nested": {"ok": True}}

        atomic_write_json(target_path, data)
        assert target_path.exists()

        with open(target_path, "r", encoding="utf-8") as f:
            read_data = json.load(f)

        assert read_data == data

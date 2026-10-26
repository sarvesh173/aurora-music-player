import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aurora-player"))

from aurora_core.dsp import EQ_PRESETS, EqualizerDSP, normalize_gains
from aurora_core.ipc import command_from_argv, encode_command
from aurora_core.lyrics import parse_lrc, plain_lyrics, parse_embedded_lyrics
from aurora_core.queue import DynamicQueue, shuffle_items
from aurora_core.streams import STREAM_STRATEGIES, build_attempts
from aurora_core.telemetry import build_status
from aurora_core.theme import contrast_ratio, make_palette, validate_palette_contrast


def track(path, title=None):
    return {"path": path, "title": title or path, "artist": "Artist", "duration": 120}


def test_dynamic_queue_reorder_and_current_position_are_stable():
    queue = DynamicQueue([track("a"), track("b"), track("c")], current_index=1)

    queue.move(0, 2)

    assert [item["path"] for item in queue.items] == ["b", "c", "a"]
    assert queue.current["path"] == "b"
    assert queue.position == 1

    queue.remove(0)
    assert [item["path"] for item in queue.items] == ["c", "a"]
    assert queue.current["path"] == "c"


def test_shuffle_items_is_seeded_without_mutating_source():
    source = [track("a"), track("b"), track("c"), track("d")]

    shuffled = shuffle_items(source, seed=22)

    assert [item["path"] for item in source] == ["a", "b", "c", "d"]
    assert [item["path"] for item in shuffled] == ["d", "c", "a", "b"]


def test_lrc_parser_supports_multiple_timestamps_and_plain_lyrics():
    assert parse_lrc("[00:01.50][00:03]Hello\n[01:02.250]World") == [
        (1500, "Hello"),
        (3000, "Hello"),
        (62250, "World"),
    ]
    assert plain_lyrics("one\n\ntwo") == [(0, "one"), (5000, "two")]


def test_embedded_lyrics_detect_lrc_and_plain_text():
    assert parse_embedded_lyrics("[00:04.00]Embedded") == {
        "lines": [(4000, "Embedded")],
        "source": "embedded-uslt",
        "synced": True,
    }
    assert parse_embedded_lyrics("First line\nSecond line")["synced"] is False


def test_eq_validation_and_processing_are_bounded():
    gains = normalize_gains([99, -99, 1])
    assert gains == [12, -12, 1, 0, 0, 0, 0, 0, 0, 0]
    assert "Acoustic" in EQ_PRESETS

    dsp = EqualizerDSP(sample_rate=44100, channels=1)
    output = dsp.process([0.0, 0.25, -0.25, 1.5, -1.5], [0] * 10)
    assert len(output) == 5
    assert max(abs(sample) for sample in output) <= 1.0


def test_light_palette_meets_contrast_contract():
    palette = make_palette(239, mode="light")

    assert contrast_ratio(palette["on_surface"], palette["surface"]) >= 4.5
    assert validate_palette_contrast(palette)


def test_status_contract_contains_v22_agent_fields():
    status = build_status(
        state="playing",
        track=track("/music/a.mp3", "A"),
        position_ms=1200,
        queue=[track("/music/a.mp3", "A"), track("/music/b.mp3", "B")],
        queue_index=0,
        volume=0.7,
        eq={"enabled": True, "preset": "Bass Boost", "gains": [8] + [0] * 9},
        buffer_health=0.75,
        bitrate=192000,
    )

    assert status["duration_ms"] == 120000
    assert status["bit_rate_kbps"] == 192
    assert status["buffer_health"] == 0.75
    assert status["queue_position"] == 1
    assert status["eq_preset"] == "Bass Boost"
    json.dumps(status)


def test_ipc_command_contract_is_json_lines_friendly():
    command = command_from_argv(["--volume", "0.65"])
    decoded = json.loads(encode_command(command))

    assert decoded["command"] == "volume"
    assert decoded["args"] == ["0.65"]


def test_stream_strategy_order_is_stable():
    assert STREAM_STRATEGIES[0] == "cookies-from-browser"
    assert STREAM_STRATEGIES[-1] == "plain-ytdlp"
    assert [name for name, _ in build_attempts("https://example.com/audio")][-4:] == [
        "client-rotation",
        "invidious",
        "innertube",
        "plain-ytdlp",
    ]

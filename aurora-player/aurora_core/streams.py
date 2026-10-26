"""Resilient yt-dlp stream resolution contracts."""

import subprocess
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence


STREAM_STRATEGIES = (
    "cookies-from-browser",
    "cookies-file",
    "client-rotation",
    "invidious",
    "innertube",
    "plain-ytdlp",
)


@dataclass
class StreamResolution:
    url: str
    strategy: str
    duration_ms: int = 0
    bitrate_kbps: int = 0


def build_attempts(url: str, config: Optional[Dict[str, str]] = None) -> List[Sequence[str]]:
    """Build safe yt-dlp attempts in the documented fallback order."""

    config = config or {}
    binary = config.get("binary", "yt-dlp")
    common = [binary, "--no-warnings", "--no-playlist", "--get-url", "-f", "bestaudio/best"]
    attempts: List[Sequence[str]] = []
    browser = config.get("browser")
    cookies = config.get("cookies_file")
    if browser:
        attempts.append(common + ["--cookies-from-browser", browser, url])
    if cookies:
        attempts.append(common + ["--cookies", cookies, url])
    attempts.append(common + ["--extractor-args", "youtube:player_client=ios,android,tv,web,web_safari", url])
    attempts.append(common + [url])
    return attempts


def resolve_stream(
    url: str,
    config: Optional[Dict[str, str]] = None,
    runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
) -> StreamResolution:
    """Resolve the first usable direct audio URL, raising a useful error."""

    if not url or not url.startswith(("http://", "https://")):
        raise ValueError("stream URL must be http:// or https://")
    runner = runner or subprocess.run
    errors = []
    for index, command in enumerate(build_attempts(url, config)):
        strategy = STREAM_STRATEGIES[min(index, len(STREAM_STRATEGIES) - 1)]
        try:
            result = runner(command, check=False, capture_output=True, text=True, timeout=20)
            output = (result.stdout or "").strip().splitlines()
            if result.returncode == 0 and output and output[0].startswith(("http://", "https://")):
                return StreamResolution(output[0], strategy)
            errors.append(f"{strategy}: {result.stderr.strip()[-160:]}")
        except Exception as exc:
            errors.append(f"{strategy}: {exc}")
    raise RuntimeError("unable to resolve stream: " + "; ".join(errors))

"""Unix-domain JSON-lines IPC with safe command parsing."""

import json
import os
import socket
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional


COMMAND_ALIASES = {
    "--play": "play",
    "--pause": "pause",
    "--toggle": "toggle",
    "--stop": "stop",
    "--next": "next",
    "--prev": "prev",
    "--previous": "prev",
    "--play-file": "play-file",
    "--play-url": "play-url",
    "--queue-add": "queue-file",
    "--queue-file": "queue-file",
    "--queue-next": "queue-next-file",
    "--queue-next-file": "queue-next-file",
    "--queue-remove": "queue-remove",
    "--queue-clear": "queue-clear",
    "--volume": "volume",
    "--seek": "seek",
    "--setpos": "setpos",
    "--set-theme": "set-theme",
    "--set-mode": "set-mode",
    "--theme-mode": "set-mode",
    "--eq-preset": "eq-preset",
    "--eq-gain": "eq-gain",
    "--sleep-timer": "sleep-timer",
    "--cancel-sleep": "cancel-sleep",
    "--new-playlist": "new-playlist",
    "--add-to-playlist": "add-to-playlist",
    "--play-playlist": "play-playlist",
    "--browse-search": "browse-search",
    "--browse-country": "browse-country",
    "--browse-load-more": "browse-load-more",
    "--browse-download": "browse-download",
}


def command_from_argv(argv: Iterable[str]) -> Dict[str, Any]:
    values = list(argv)
    if not values or values[0] not in COMMAND_ALIASES:
        raise ValueError("unsupported IPC command")
    command = COMMAND_ALIASES[values[0]]
    args = values[1:]
    if command in {"play", "pause", "toggle", "stop", "next", "prev", "queue-clear", "cancel-sleep", "browse-load-more"}:
        if args:
            raise ValueError("command does not accept arguments")
    elif command == "add-to-playlist":
        if len(args) != 2:
            raise ValueError("--add-to-playlist requires a playlist and path")
    elif command == "eq-gain":
        if len(args) != 2:
            raise ValueError("--eq-gain requires band and gain")
    elif not args:
        raise ValueError("command requires an argument")
    return {"id": uuid.uuid4().hex, "command": command, "args": args}


def encode_command(command: Dict[str, Any]) -> str:
    return json.dumps(command, separators=(",", ":")) + "\n"


def socket_path(config_dir: Path) -> Path:
    return Path(config_dir) / "aurora.sock"


class UnixJSONServer:
    """Minimal background socket server; callback ownership stays with Qt."""

    def __init__(self, path: Path, callback: Callable[[Dict[str, Any]], Any]):
        self.path = Path(path)
        self.callback = callback
        self._server: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.running:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self.path.exists():
                self.path.unlink()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(self.path))
            os.chmod(self.path, 0o600)
            server.listen(8)
            server.settimeout(0.5)
            self._server = server
            self._stop.clear()
            self._thread = threading.Thread(target=self._serve, name="aurora-ipc", daemon=True)
            self._thread.start()
            return True
        except OSError:
            self.stop()
            return False

    def _serve(self) -> None:
        while not self._stop.is_set() and self._server is not None:
            try:
                connection, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                try:
                    chunks = []
                    total = 0
                    while total < 65536:
                        chunk = connection.recv(min(4096, 65536 - total))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        total += len(chunk)
                        if b"\n" in chunk:
                            break
                    raw = b"".join(chunks).decode("utf-8")
                    payload = json.loads(raw.strip() or "{}")
                    result = self.callback(payload)
                    response = result if isinstance(result, dict) else {"ok": True}
                except Exception as exc:
                    response = {"ok": False, "error": str(exc)}
                connection.sendall((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError:
                pass


def send_json_command(path: Path, command: Dict[str, Any], timeout: float = 1.0) -> Dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall(encode_command(command).encode("utf-8"))
        response = client.recv(65536).decode("utf-8").strip()
    return json.loads(response or "{}")

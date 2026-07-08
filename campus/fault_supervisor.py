#!/usr/bin/env python3
"""Run a child process with HTTP/file-based fault-control toggles."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

TRUE_VALUES = frozenset({"1", "true", "yes", "on", "pause", "paused", "silence", "silenced"})
FALSE_VALUES = frozenset({"0", "false", "no", "off", "", "resume", "running"})


def parse_fault_state(value: str) -> bool:
    """Parse a text fault-control state value."""

    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"Invalid fault state value: {value!r}")


class FaultController:
    """Manage silencing and resuming a supervised child process."""

    def __init__(
        self,
        child_process: subprocess.Popen[str] | object,
        *,
        state_file: str | None = None,
        command: Sequence[str] | None = None,
    ):
        self.child_process = child_process
        self.state_file = Path(state_file) if state_file else None
        self.command = list(command or [])
        self._lock = threading.RLock()
        self._silenced = False
        self._last_state_text: str | None = None

    @property
    def pid(self) -> int:
        """Return the supervised child PID."""

        return int(getattr(self.child_process, "pid"))

    def is_running(self) -> bool:
        """Return whether the supervised process is still running."""

        return getattr(self.child_process, "poll")() is None

    def status(self) -> dict[str, object]:
        """Return a JSON-serializable status object."""

        with self._lock:
            return {
                "pid": self.pid,
                "running": self.is_running(),
                "silenced": self._silenced,
                "state_file": str(self.state_file) if self.state_file else None,
                "command": self.command,
            }

    def _signal_child(self, sig: int) -> None:
        if not self.is_running():
            raise RuntimeError("Fault-controlled process is no longer running")
        os.kill(self.pid, sig)

    def _persist_state(self, silenced: bool) -> None:
        if self.state_file is None:
            return
        state_text = "1\n" if silenced else "0\n"
        self.state_file.write_text(state_text)
        self._last_state_text = state_text

    def silence(self) -> dict[str, object]:
        """Pause the child process."""

        with self._lock:
            if not self._silenced:
                self._signal_child(signal.SIGSTOP)
                self._silenced = True
            self._persist_state(True)
            return self.status()

    def resume(self) -> dict[str, object]:
        """Resume the child process."""

        with self._lock:
            if self._silenced and self.is_running():
                self._signal_child(signal.SIGCONT)
            self._silenced = False
            self._persist_state(False)
            return self.status()

    def terminate(self, sig: int = signal.SIGTERM) -> None:
        """Forward a shutdown signal to the child."""

        with self._lock:
            if not self.is_running():
                return
            if self._silenced:
                os.kill(self.pid, signal.SIGCONT)
                self._silenced = False
            getattr(self.child_process, "send_signal")(sig)

    def sync_from_state_file(self) -> dict[str, object] | None:
        """Apply the current state-file value if it changed."""

        if self.state_file is None or not self.state_file.exists():
            return None

        raw_text = self.state_file.read_text()
        if raw_text == self._last_state_text:
            return None

        desired_silence = parse_fault_state(raw_text)
        self._last_state_text = raw_text
        if desired_silence:
            return self.silence()
        return self.resume()


class _FaultRequestHandler(BaseHTTPRequestHandler):
    controller: FaultController

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        logger.info("fault-control %s - %s", self.client_address[0], format % args)

    def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/fault/status":
            self._write_json(200, self.controller.status())
            return
        self._write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/fault/silence":
                self._write_json(200, self.controller.silence())
                return
            if self.path == "/fault/resume":
                self._write_json(200, self.controller.resume())
                return
        except RuntimeError as exc:
            self._write_json(409, {"error": str(exc)})
            return

        self._write_json(404, {"error": "not_found"})


def start_control_server(
    controller: FaultController, control_port: int
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    """Start the fault-control HTTP server."""

    handler_class = type("FaultRequestHandler", (_FaultRequestHandler,), {"controller": controller})
    server = ThreadingHTTPServer(("0.0.0.0", control_port), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="fault-control-api")
    thread.start()
    return server, thread


def start_state_watcher(
    controller: FaultController, *, poll_interval: float = 0.5
) -> tuple[threading.Event, threading.Thread] | None:
    """Start polling the optional state file for changes."""

    if controller.state_file is None:
        return None

    stop_event = threading.Event()

    def watch() -> None:
        while not stop_event.wait(poll_interval):
            try:
                controller.sync_from_state_file()
            except Exception:
                logger.exception("Fault state-file sync failed")

    thread = threading.Thread(target=watch, daemon=True, name="fault-state-watch")
    thread.start()
    return stop_event, thread


def run_supervised_command(
    command: Sequence[str], *, control_port: int | None = None, state_file: str | None = None
) -> int:
    """Run a supervised child command until it exits."""

    child = subprocess.Popen(list(command), text=True)
    controller = FaultController(child, state_file=state_file, command=command)
    if state_file is None or not Path(state_file).exists():
        controller.resume()

    server: ThreadingHTTPServer | None = None
    watcher: tuple[threading.Event, threading.Thread] | None = None

    if control_port is not None:
        server, _thread = start_control_server(controller, control_port)
        logger.info("Fault-control HTTP API listening on port %d", control_port)

    watcher = start_state_watcher(controller)
    if watcher:
        try:
            controller.sync_from_state_file()
        except Exception:
            logger.exception("Initial fault state-file sync failed")

    original_handlers: dict[int, object] = {}

    def handle_signal(sig: int, _frame) -> None:
        logger.info("Forwarding signal %s to child process", sig)
        controller.terminate(sig)

    for sig in (signal.SIGINT, signal.SIGTERM):
        original_handlers[sig] = signal.getsignal(sig)
        signal.signal(sig, handle_signal)

    try:
        return child.wait()
    finally:
        if watcher:
            watcher[0].set()
            watcher[1].join(timeout=1)
        if server is not None:
            server.shutdown()
            server.server_close()
        for sig, handler in original_handlers.items():
            signal.signal(sig, handler)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fault-control supervisor for BACnet test processes"
    )
    parser.add_argument("--control-port", type=int, help="HTTP control port for /fault/* endpoints")
    parser.add_argument("--state-file", help="Optional file path containing 1/0 silence state")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    args = _parse_args(argv or sys.argv[1:])
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("fault_supervisor requires a command after --")

    return run_supervised_command(
        command,
        control_port=args.control_port,
        state_file=args.state_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())

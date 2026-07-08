"""Tests for the campus fault-control supervisor."""

from __future__ import annotations

import json
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from campus.fault_supervisor import FaultController, _FaultRequestHandler


class _FakeProcess:
    def __init__(self, pid: int = 4321):
        self.pid = pid
        self.returncode = None
        self.signals: list[int] = []

    def poll(self):
        return self.returncode

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)


class TestFaultSupervisor(unittest.TestCase):
    """Validate HTTP and file-based fault control."""

    def test_state_file_sync_silences_and_resumes_process(self):
        process = _FakeProcess()
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "fault.state"
            state_file.write_text("1\n")

            controller = FaultController(process, state_file=str(state_file))
            with patch("campus.fault_supervisor.os.kill") as kill:
                controller.sync_from_state_file()
                kill.assert_called_once()
                self.assertTrue(controller.status()["silenced"])

                state_file.write_text("0\n")
                controller.sync_from_state_file()
                self.assertEqual(kill.call_count, 2)
                self.assertFalse(controller.status()["silenced"])

    def test_http_control_endpoints_toggle_process_state(self):
        process = _FakeProcess()
        controller = FaultController(process)

        with patch("campus.fault_supervisor.os.kill") as kill:
            handler_class = type(
                "TestFaultHandler", (_FaultRequestHandler,), {"controller": controller}
            )

            def make_handler(path: str):
                handler = object.__new__(handler_class)
                handler.path = path
                handler.wfile = BytesIO()
                handler.send_response = lambda _code: None
                handler.send_header = lambda _key, _value: None
                handler.end_headers = lambda: None
                return handler

            status_handler = make_handler("/fault/status")
            status_handler.do_GET()
            status = json.loads(status_handler.wfile.getvalue().decode("utf-8"))
            self.assertFalse(status["silenced"])

            silence_handler = make_handler("/fault/silence")
            silence_handler.do_POST()
            silenced = json.loads(silence_handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(silenced["silenced"])

            resume_handler = make_handler("/fault/resume")
            resume_handler.do_POST()
            resumed = json.loads(resume_handler.wfile.getvalue().decode("utf-8"))
            self.assertFalse(resumed["silenced"])

        self.assertEqual(kill.call_count, 2)


if __name__ == "__main__":
    unittest.main()

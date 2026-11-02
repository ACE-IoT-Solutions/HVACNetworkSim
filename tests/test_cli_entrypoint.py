"""The supported launcher publishes the endpoints it enables."""

import runpy
from pathlib import Path
from unittest.mock import patch


CLI = runpy.run_path(str(Path(__file__).resolve().parents[1] / "hvac-sim"))


def test_gateway_mode_publishes_modbus_and_bacnet_ports():
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        result = CLI["run_simulation"](
            runtime="docker", extra_env={"MODBUS_MODE": "gateway", "MODBUS_PORT": "5021"}
        )
    assert result == 0
    command = run.call_args.args[0]
    assert [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-p"] == [
        "47808:47808/udp",
        "5021:5021/tcp",
    ]


def test_direct_mode_requires_host_network_for_meter_ports():
    with patch("subprocess.run") as run:
        result = CLI["run_simulation"](runtime="docker", extra_env={"MODBUS_MODE": "direct"})
    assert result == 1
    run.assert_not_called()

#!/usr/bin/env python3
"""Runtime wrapper for campus BBMD containers."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from campus.bbmd_runtime import parse_rendered_bbmd_config, render_bbmd_config  # noqa: E402
from campus.bbmd_runtime import normalize_bdt_peer_entry  # noqa: E402
from campus.fault_supervisor import run_supervised_command  # noqa: E402

logger = logging.getLogger(__name__)

TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


def parse_boolean(value: str, *, variable_name: str) -> bool:
    """Parse a strict boolean environment variable."""

    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(
        f"{variable_name} must be one of: {', '.join(sorted(TRUE_VALUES | FALSE_VALUES))}"
    )


def split_bdt_peer_env(value: str) -> list[str]:
    """Split a comma-separated BDT peer env var."""

    peers = [entry.strip() for entry in value.split(",")]
    if not peers or any(not entry for entry in peers):
        raise ValueError("BBMD_BDT_PEERS must be a comma-separated list of ip:port entries")
    return peers


def apply_bbmd_env_overrides(config_text: str) -> str:
    """Apply supported BBMD env var overrides to a rendered config file."""

    base_config = parse_rendered_bbmd_config(config_text)
    if not base_config:
        raise ValueError("Unable to parse generated BBMD config")

    bbmd_address = os.getenv("BBMD_ADDRESS", str(base_config["bbmd_address"]))
    device_id = int(os.getenv("BBMD_DEVICE_ID", str(base_config["device_id"])))
    device_name = os.getenv("BBMD_DEVICE_NAME", str(base_config["device_name"]))
    foreign_devices = parse_boolean(
        os.getenv(
            "BBMD_ACCEPT_FOREIGN_DEVICES",
            "true" if bool(base_config["accept_foreign_devices"]) else "false",
        ),
        variable_name="BBMD_ACCEPT_FOREIGN_DEVICES",
    )

    bdt_override = os.getenv("BBMD_BDT_PEERS")
    if bdt_override:
        self_ip = bbmd_address.split("/", 1)[0]
        bdt_entries = [
            normalize_bdt_peer_entry(entry, self_ip=self_ip)
            for entry in split_bdt_peer_env(bdt_override)
        ]
    else:
        bdt_entries = list(base_config.get("bdt_entries", []))  # type: ignore[arg-type]

    if parse_boolean(os.getenv("BBMD_BDT_STALE", "false"), variable_name="BBMD_BDT_STALE"):
        logger.warning(
            "BBMD_BDT_STALE is not enforced by ace-acl-bbmd; using a static startup config"
        )

    return render_bbmd_config(
        bbmd_address=bbmd_address,
        device_id=device_id,
        device_name=device_name,
        bdt_entries=bdt_entries,
        accept_foreign_devices=foreign_devices,
    )


def add_routes(routes: Sequence[str]) -> None:
    """Install any requested subnet routes for the BBMD."""

    for route in routes:
        try:
            destination, netmask, gateway = route.split(":", 2)
        except ValueError:
            raise ValueError(f"Invalid --route value: {route}") from None

        result = subprocess.run(
            ["python3", "/app/campus/add_route.py", destination, netmask, gateway],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("Added route %s/%s via %s", destination, netmask, gateway)
            continue

        logger.warning(
            "Failed to add route %s/%s via %s: %s",
            destination,
            netmask,
            gateway,
            result.stderr.strip() or result.stdout.strip() or "unknown error",
        )


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run ace-acl-bbmd with campus fault controls")
    parser.add_argument("--config", required=True, help="Base BBMD config path")
    parser.add_argument("--acl", required=True, help="ACL rules path")
    parser.add_argument("--control-port", type=int, help="Optional fault-control HTTP port")
    parser.add_argument("--state-file", help="Optional file path containing 1/0 silence state")
    parser.add_argument(
        "--route",
        action="append",
        default=[],
        metavar="DEST:NETMASK:GATEWAY",
        help="Route to add before launching the BBMD",
    )
    args = parser.parse_args(argv)

    add_routes(args.route)

    base_config = Path(args.config).read_text()
    effective_config = apply_bbmd_env_overrides(base_config)
    effective_path = Path("/tmp/bbmd_config.effective.yaml")
    effective_path.write_text(effective_config)

    command = [
        "ace-acl-bbmd",
        "--config",
        str(effective_path),
        "--acl",
        args.acl,
    ]
    return run_supervised_command(
        command,
        control_port=args.control_port,
        state_file=args.state_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())

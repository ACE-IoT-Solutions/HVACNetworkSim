"""Shared BBMD config helpers for campus generation and runtime wrappers."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class BBMDIdentity:
    """Static BBMD identity for a building subnet."""

    address: str
    device_id: int
    device_name: str


_CONFIG_PATTERNS = {
    "bbmd_address": re.compile(r'^bbmd_address:\s*"?(?P<value>[^"]+)"?\s*$'),
    "device_id": re.compile(r"^device_id:\s*(?P<value>\d+)\s*$"),
    "device_name": re.compile(r'^device_name:\s*"(?P<value>[^"]+)"\s*$'),
    "accept_foreign_devices": re.compile(r"^accept_foreign_devices:\s*(?P<value>true|false)\s*$"),
}

CAMPUS_BBMD_HOST_ADDRESS = 100


def campus_host_ip(building_index: int, host_address: int) -> str:
    """Return a campus subnet IP for a building-local host address."""

    return f"10.{building_index}.0.{host_address}"


def get_bbmd_identity(building_index: int) -> BBMDIdentity:
    """Return the canonical BBMD identity for a building."""

    building_ip = campus_host_ip(building_index, CAMPUS_BBMD_HOST_ADDRESS)
    return BBMDIdentity(
        address=f"{building_ip}/24:47808",
        device_id=building_index * 1000 - 2,
        device_name=f"BBMD-Building{building_index}",
    )


def normalize_bdt_peer_entry(entry: str, *, self_ip: str) -> str:
    """Normalize a BDT peer entry to ``IP/CIDR:PORT`` form."""

    value = entry.strip()
    if not value:
        raise ValueError("BDT peer entries must not be empty")

    try:
        host_part, port_part = value.rsplit(":", 1)
    except ValueError as exc:
        raise ValueError(f"Invalid BDT peer entry: {entry}") from exc

    try:
        port = int(port_part)
    except ValueError as exc:
        raise ValueError(f"Invalid BDT peer port in entry: {entry}") from exc

    if port < 1 or port > 65535:
        raise ValueError(f"Invalid BDT peer port in entry: {entry}")

    if "/" in host_part:
        interface = ipaddress.IPv4Interface(host_part)
        ip_value = str(interface.ip)
        prefixlen = interface.network.prefixlen
    else:
        ip_value = str(ipaddress.IPv4Address(host_part))
        prefixlen = 24 if ip_value == self_ip else 32

    return f"{ip_value}/{prefixlen}:{port}"


def default_bdt_entries(building_index: int, num_buildings: int) -> list[str]:
    """Return the default symmetric BDT entries for a campus building."""

    self_ip = campus_host_ip(building_index, CAMPUS_BBMD_HOST_ADDRESS)
    entries = [f"{self_ip}/24:47808"]
    for peer_index in range(1, num_buildings + 1):
        if peer_index == building_index:
            continue
        entries.append(f"{campus_host_ip(peer_index, CAMPUS_BBMD_HOST_ADDRESS)}/32:47808")
    return entries


def build_bdt_entries(
    building_index: int,
    num_buildings: int,
    peer_overrides: Iterable[str] | None = None,
) -> list[str]:
    """Build normalized BDT entries for a building."""

    if peer_overrides is None:
        return default_bdt_entries(building_index, num_buildings)

    identity = get_bbmd_identity(building_index)
    self_ip = identity.address.split("/", 1)[0]
    entries: list[str] = []
    seen: set[str] = set()

    for entry in peer_overrides:
        normalized = normalize_bdt_peer_entry(entry, self_ip=self_ip)
        if normalized in seen:
            continue
        seen.add(normalized)
        entries.append(normalized)

    return entries


def render_bbmd_config(
    *,
    bbmd_address: str,
    device_id: int,
    device_name: str,
    bdt_entries: Iterable[str],
    accept_foreign_devices: bool,
) -> str:
    """Render a BBMD config YAML document."""

    bdt_lines = "\n".join(f'  - "{entry}"' for entry in bdt_entries)
    foreign_devices = "true" if accept_foreign_devices else "false"

    return f"""bbmd_address: "{bbmd_address}"
device_id: {device_id}
device_name: "{device_name}"
bdt_entries:
{bdt_lines}
accept_foreign_devices: {foreign_devices}
log_level: "INFO"
enable_metrics: true
metrics_http_port: 9090
"""


def parse_rendered_bbmd_config(config_text: str) -> dict[str, object]:
    """Parse the generated BBMD YAML format used by this repo."""

    parsed: dict[str, object] = {}
    lines = config_text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        for key, pattern in _CONFIG_PATTERNS.items():
            match = pattern.match(line)
            if not match:
                continue

            value = match.group("value")
            if key == "device_id":
                parsed[key] = int(value)
            elif key == "accept_foreign_devices":
                parsed[key] = value == "true"
            else:
                parsed[key] = value
            break

        if line.strip() == "bdt_entries:":
            entries: list[str] = []
            index += 1
            while index < len(lines):
                entry_line = lines[index]
                if not entry_line.startswith("  - "):
                    index -= 1
                    break
                entries.append(entry_line.split('"', 2)[1])
                index += 1
            parsed["bdt_entries"] = entries

        index += 1

    return parsed

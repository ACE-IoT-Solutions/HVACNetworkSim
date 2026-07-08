#!/usr/bin/env python3
"""
Campus Compose Generator - Generate docker-compose and BBMD configs from a campus TTL file.

Parses a Brick schema campus TTL file and generates:
- docker-compose.campus.yml with per-building networks, BBMD and sim services
- campus/configs/bbmd{N}/bbmd_config.yaml and acl_rules.yaml per building

Network architecture (example with 2 buildings):

    Building 1 Network (10.1.0.0/24)       Building 2 Network (10.2.0.0/24)
    ├── BBMD1 (10.1.0.100/24:47808)        ├── BBMD2 (10.2.0.100/24:47808)
    ├── Sim1 (10.1.0.101)                  ├── Sim2 (10.2.0.101)
    └── Router (10.1.0.102)                └── Router (10.2.0.102)

    BBMDs peer via direct IP routing through the campus router:
    BBMD1 BDT: self (10.1.0.100/24) + peer (10.2.0.100/24)
    BBMD2 BDT: self (10.2.0.100/24) + peer (10.1.0.100/24)

    Campus router enables IP routing between building subnets.
    All containers (sims + BBMDs) have static routes via the router.
    Host port mapping retained for external scanner access.

Usage:
    python campus/generate_campus.py examples/multi_building_campus.ttl
    python campus/generate_campus.py examples/large_campus.ttl
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Add project root to path so we can import src modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from campus.bbmd_runtime import (  # noqa: E402
    CAMPUS_BBMD_HOST_ADDRESS,
    build_bdt_entries,
    campus_host_ip,
    get_bbmd_identity,
    render_bbmd_config,
)


def parse_campus(ttl_file: str):
    """Parse a campus TTL file and return the CampusStructure."""
    from src.brick.parser import BrickParser

    parser = BrickParser(ttl_file)
    return parser.extract_all_buildings()


# Base host port for BBMD port mapping (external access): building i gets port BASE + i
BBMD_HOST_PORT_BASE = 47808
BBMD_CONTROL_PORT = 9100
BBMD_CONTROL_HOST_PORT_BASE = 19100
SIM_CONTROL_PORT = 9100
SIM_CONTROL_HOST_PORT_BASE = 19200
DEFAULT_CAMPUS_SCENARIO = "default"
CAMPUS_SIM_HOST_ADDRESS = 101
CAMPUS_ROUTER_HOST_ADDRESS = 102
CAMPUS_ROUTER_COMPAT_HOST_ADDRESS = 254


@dataclass(frozen=True)
class CampusScenario:
    default_ttl: str
    explicit_network_numbers: bool = False
    bbmd_bdt_peer_overrides: dict[int, tuple[str, ...]] = field(default_factory=dict)
    router_claim_overrides: dict[int, tuple[int, ...]] = field(default_factory=dict)


CAMPUS_SCENARIOS = {
    "default": CampusScenario(default_ttl="examples/multi_building_campus.ttl"),
    "multi-network": CampusScenario(
        default_ttl="examples/multi_building_campus.ttl",
        explicit_network_numbers=True,
    ),
    "multi-network-collisions": CampusScenario(
        default_ttl="examples/multi_building_campus_collisions.ttl",
        explicit_network_numbers=True,
    ),
    "multi-network-bdt-asymmetry": CampusScenario(
        default_ttl="examples/multi_building_campus.ttl",
        explicit_network_numbers=True,
        bbmd_bdt_peer_overrides={
            2: (f"10.2.0.{CAMPUS_BBMD_HOST_ADDRESS}:47808",),
        },
    ),
    "multi-network-duplicate-router-claim": CampusScenario(
        default_ttl="examples/multi_building_campus.ttl",
        explicit_network_numbers=True,
        router_claim_overrides={
            1: (2100,),
        },
    ),
}


def resolve_campus_ttl(ttl_file: str | None, scenario: str) -> Path:
    """Resolve the input TTL path or the built-in example for a scenario."""

    if ttl_file:
        ttl_path = Path(ttl_file)
        if not ttl_path.is_absolute():
            ttl_path = PROJECT_ROOT / ttl_path
        return ttl_path.resolve()

    scenario_ttl = PROJECT_ROOT / CAMPUS_SCENARIOS[scenario].default_ttl
    return scenario_ttl.resolve()


def get_scenario_network_number(building_index: int, scenario: str) -> int | None:
    """Return an explicit BACnet network number for scenario-driven campuses."""

    if not CAMPUS_SCENARIOS[scenario].explicit_network_numbers:
        return None
    return building_index * 100


def get_scenario_router_claims(building_index: int, scenario: str) -> tuple[int, ...]:
    """Return any extra router claims configured for a scenario."""

    return CAMPUS_SCENARIOS[scenario].router_claim_overrides.get(building_index, ())


def get_scenario_bdt_peer_overrides(building_index: int, scenario: str) -> tuple[str, ...] | None:
    """Return any explicit BDT peer overrides for a scenario."""

    return CAMPUS_SCENARIOS[scenario].bbmd_bdt_peer_overrides.get(building_index)


def yaml_quote(value: str) -> str:
    """Quote a scalar safely for YAML output."""

    return json.dumps(value)


def generate_bbmd_config(
    building_index: int,
    num_buildings: int,
    expose_bacnet: bool = False,
    peer_entries: tuple[str, ...] | None = None,
) -> str:
    """Generate BBMD config YAML for a building.

    Each BBMD is configured with its building subnet address and peers with
    other BBMDs via direct IP routing through the campus router.

    The BDT (Broadcast Distribution Table) must include ALL BBMDs per the
    BACnet standard, including self. BIPBBMD checks self.bbmdAddress in
    self.bbmdBDT before locally rebroadcasting forwarded packets.

    Args:
        building_index: 1-based building index
        num_buildings: Total number of buildings (for peer list)
    """
    identity = get_bbmd_identity(building_index)
    bdt_entries = build_bdt_entries(building_index, num_buildings, peer_entries)
    return render_bbmd_config(
        bbmd_address=identity.address,
        device_id=identity.device_id,
        device_name=identity.device_name,
        bdt_entries=bdt_entries,
        accept_foreign_devices=expose_bacnet,
    )


def generate_acl_config() -> str:
    """Generate an allow-all ACL rules YAML."""
    return """default_action: allow
log_default: false
rules:
  - name: "allow_all_traffic"
    action: allow
    priority: 10
    message_types: [all]
"""


def generate_compose(
    campus,
    ttl_file: str,
    bbmd_image: str = "ace-acl-bbmd",
    expose_bacnet: bool = False,
    scenario: str = DEFAULT_CAMPUS_SCENARIO,
) -> str:
    """Generate docker-compose.campus.yml content.

    Args:
        campus: CampusStructure from BrickParser
        ttl_file: Path to the campus TTL file (relative to project root)
        bbmd_image: BBMD container image name
    """
    buildings = list(campus.buildings.items())
    num_buildings = len(buildings)

    # Resolve TTL file path relative to project root
    ttl_path = Path(ttl_file).resolve()
    try:
        ttl_relative = ttl_path.relative_to(PROJECT_ROOT)
    except ValueError:
        ttl_relative = ttl_path

    # Header
    lines = [
        "# Auto-generated campus compose file",
        f"# Source: {ttl_relative}",
        f"# Buildings: {num_buildings}",
        f"# Scenario: {scenario}",
        "",
        "networks:",
    ]

    # Building networks (BBMDs peer via direct IP routing through campus router)
    # internal: true prevents the podman bridge gateway from routing between subnets,
    # which would create phantom BBMDs visible to scanners at the gateway IP.
    # Only the campus-router container should route between building subnets.
    for i in range(1, num_buildings + 1):
        lines.extend(
            [
                f"  building{i}:",
                "    driver: bridge",
                "    internal: true",
                "    ipam:",
                "      config:",
                f"        - subnet: 10.{i}.0.0/24",
            ]
        )

    lines.extend(["", "services:"])

    # Generate services for each building
    for i, (building_name, _building) in enumerate(buildings, 1):
        building_ip = campus_host_ip(i, CAMPUS_BBMD_HOST_ADDRESS)
        sim_ip = campus_host_ip(i, CAMPUS_SIM_HOST_ADDRESS)
        router_ip = campus_host_ip(i, CAMPUS_ROUTER_HOST_ADDRESS)
        host_port = BBMD_HOST_PORT_BASE + i
        bbmd_control_host_port = BBMD_CONTROL_HOST_PORT_BASE + i
        sim_control_host_port = SIM_CONTROL_HOST_PORT_BASE + i
        network_number = get_scenario_network_number(i, scenario)
        router_claims = get_scenario_router_claims(i, scenario)
        bdt_peer_overrides = get_scenario_bdt_peer_overrides(i, scenario)
        bbmd_identity = get_bbmd_identity(i)
        safe_name = re.sub(r"[^a-z0-9_.]+", "_", building_name.lower()).strip("_")
        if not safe_name:
            safe_name = f"building_{i}"

        # Build route-add commands for the BBMD to reach other building subnets.
        bbmd_route_specs = []
        for j in range(1, num_buildings + 1):
            if j != i:
                bbmd_route_specs.append(f"10.{j}.0.0:255.255.255.0:{router_ip}")

        # BBMD service - on building network, with routes to peer subnets
        lines.extend(
            [
                f"  bbmd{i}:",
                f"    image: {bbmd_image}",
                f"    container_name: campus-bbmd{i}",
                "    networks:",
                f"      building{i}:",
                f"        ipv4_address: {building_ip}",
                "    environment:",
                f'      FAULT_CONTROL_PORT: "{BBMD_CONTROL_PORT}"',
                '      FAULT_CONTROL_STATE_FILE: "/tmp/bbmd-fault-control.state"',
                f"      BBMD_ADDRESS: {yaml_quote(bbmd_identity.address)}",
                f'      BBMD_DEVICE_ID: "{bbmd_identity.device_id}"',
                f"      BBMD_DEVICE_NAME: {yaml_quote(bbmd_identity.device_name)}",
                f"      BBMD_ACCEPT_FOREIGN_DEVICES: {'true' if expose_bacnet else 'false'}",
            ]
        )
        if network_number is not None:
            lines.append(f'      BACNET_NETWORK_NUMBER: "{network_number}"')
        if bdt_peer_overrides is not None:
            lines.append(f"      BBMD_BDT_PEERS: {yaml_quote(','.join(bdt_peer_overrides))}")
        lines.extend(
            [
                "    ports:",
                f'      - "127.0.0.1:{bbmd_control_host_port}:{BBMD_CONTROL_PORT}/tcp"',
            ]
        )
        if expose_bacnet:
            lines.append(f'      - "{host_port}:47808/udp"')
        lines.extend(
            [
                "    volumes:",
                f"      - ./campus/configs/bbmd{i}/bbmd_config.yaml:/app/config/bbmd_config.yaml:ro",
                f"      - ./campus/configs/bbmd{i}/acl_rules.yaml:/app/config/acl_rules.yaml:ro",
                "      - ./campus:/app/campus:ro",
            ]
        )
        if num_buildings > 1:
            lines.extend(
                [
                    "    cap_add:",
                    "      - NET_ADMIN",
                ]
            )
        lines.extend(
            [
                "    entrypoint:",
                "      - python3",
                "      - /app/campus/run_bbmd_service.py",
                "    command:",
                "      - --config",
                "      - /app/config/bbmd_config.yaml",
                "      - --acl",
                "      - /app/config/acl_rules.yaml",
                "      - --control-port",
                f'      - "{BBMD_CONTROL_PORT}"',
                "      - --state-file",
                "      - /tmp/bbmd-fault-control.state",
            ]
        )
        for route_spec in bbmd_route_specs:
            lines.extend(
                [
                    "      - --route",
                    f"      - {yaml_quote(route_spec)}",
                ]
            )
        if num_buildings > 1:
            lines.extend(
                [
                    "    depends_on:",
                    "      - campus-router",
                ]
            )
        lines.extend(
            [
                "    restart: unless-stopped",
                "",
            ]
        )

        # Build CAMPUS_ROUTES for this sim: routes to all other building subnets
        # via the router in this building subnet.
        routes = []
        for j in range(1, num_buildings + 1):
            if j != i:
                routes.append(f"10.{j}.0.0/24:{router_ip}")
        campus_routes = ",".join(routes)

        # HVAC sim service
        sim_lines = [
            f"  sim{i}:",
            "    image: hvac-simulator",
            f"    container_name: campus-sim-{safe_name}",
            "    networks:",
            f"      building{i}:",
            f"        ipv4_address: {sim_ip}",
            "    volumes:",
            f"      - {yaml_quote(f'./{ttl_relative.parent}:/app/brick_schemas:ro')}",
            "    environment:",
            '      SIMULATION_MODE: "brick"',
            f"      BRICK_TTL_FILE: {yaml_quote(f'/app/brick_schemas/{ttl_relative.name}')}",
            f"      BUILDING_NAME: {yaml_quote(building_name)}",
            '      BACNET_SUBNET: "24"',
            f'      FAULT_CONTROL_PORT: "{SIM_CONTROL_PORT}"',
            '      FAULT_CONTROL_STATE_FILE: "/tmp/sim-fault-control.state"',
        ]
        if network_number is not None:
            sim_lines.append(f'      BACNET_NETWORK_NUMBER: "{network_number}"')
        if campus_routes:
            sim_lines.append(f"      CAMPUS_ROUTES: {yaml_quote(campus_routes)}")
        if router_claims:
            sim_lines.append(
                f"      ROUTER_CLAIMED_NETWORKS: {yaml_quote(','.join(str(n) for n in router_claims))}"
            )
        sim_lines.extend(
            [
                "    ports:",
                f'      - "127.0.0.1:{sim_control_host_port}:{SIM_CONTROL_PORT}/tcp"',
            ]
        )
        if num_buildings > 1:
            sim_lines.extend(
                [
                    "    cap_add:",
                    "      - NET_ADMIN",
                ]
            )
        sim_lines.extend(
            [
                "    restart: unless-stopped",
                "    depends_on:",
                f"      - bbmd{i}",
            ]
        )
        if num_buildings > 1:
            sim_lines.append("      - campus-router")
        sim_lines.append("")
        lines.extend(sim_lines)

    # IP router container - connects to all building networks for unicast routing
    # Without this, BBMDs can forward broadcasts but unicast BACnet traffic
    # (ReadProperty, WriteProperty) can't reach devices on other subnets
    if num_buildings > 1:
        lines.extend(
            [
                "  campus-router:",
                "    image: alpine:3.19",
                "    container_name: campus-router",
                "    networks:",
            ]
        )
        for i in range(1, num_buildings + 1):
            lines.extend(
                [
                    f"      building{i}:",
                    f"        ipv4_address: {campus_host_ip(i, CAMPUS_ROUTER_HOST_ADDRESS)}",
                ]
            )
        lines.extend(
            [
                "    cap_add:",
                "      - NET_ADMIN",
                "    sysctls:",
                "      - net.ipv4.ip_forward=1",
            ]
        )

        # ip_forward=1 via sysctl handles forwarding; no iptables needed in alpine.
        # Keep the former .254 router address as an alias so existing scanner
        # containers with routes via 10.N.0.254 continue to work.
        router_cmds = []
        for i in range(1, num_buildings + 1):
            router_cmds.append(
                "for iface in eth0 eth1 eth2 eth3 eth4 eth5; do "
                f"ip -4 addr show dev \"$$iface\" 2>/dev/null | grep -q '10.{i}.0.{CAMPUS_ROUTER_HOST_ADDRESS}/24' "
                f'&& ip addr add 10.{i}.0.{CAMPUS_ROUTER_COMPAT_HOST_ADDRESS}/24 dev "$$iface" 2>/dev/null || true; '
                "done"
            )
            router_cmds.append(
                f"echo 'Connected to building{i}: 10.{i}.0.0/24 via "
                f"10.{i}.0.{CAMPUS_ROUTER_HOST_ADDRESS} "
                f"(compat 10.{i}.0.{CAMPUS_ROUTER_COMPAT_HOST_ADDRESS})'"
            )
        router_cmds.append("echo 'IP forwarding enabled, campus router ready'")
        router_cmds.append("sleep infinity")

        lines.extend(
            [
                "    entrypoint:",
                "      - /bin/sh",
                "      - -c",
                "      - |",
                "        " + " && \\\n        ".join(router_cmds),
                "    restart: unless-stopped",
                "",
            ]
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate campus compose and BBMD config files from a Brick TTL file"
    )
    parser.add_argument(
        "ttl_file",
        nargs="?",
        help="Campus Brick TTL file (optional when using a built-in scenario example)",
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(CAMPUS_SCENARIOS),
        default=DEFAULT_CAMPUS_SCENARIO,
        help="Campus scenario profile to generate",
    )
    parser.add_argument(
        "--expose-bacnet",
        action="store_true",
        help="Publish BBMD host ports and allow foreign-device registration",
    )
    args = parser.parse_args()

    ttl_path = resolve_campus_ttl(args.ttl_file, args.scenario)

    if not ttl_path.exists():
        print(f"Error: TTL file not found: {ttl_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing campus TTL: {ttl_path}")
    print(f"Scenario: {args.scenario}")
    campus = parse_campus(str(ttl_path))

    buildings = list(campus.buildings.items())
    num_buildings = len(buildings)
    print(f"Found {num_buildings} buildings:")
    for name, building in buildings:
        summary = building.get_equipment_summary()
        print(
            f"  {name}: {summary['ahus']} AHUs, {summary['vavs']} VAVs, "
            f"{summary['chillers']} chillers, {summary['boilers']} boilers"
        )

    # Generate BBMD configs
    configs_dir = PROJECT_ROOT / "campus" / "configs"
    for i in range(1, num_buildings + 1):
        bbmd_dir = configs_dir / f"bbmd{i}"
        bbmd_dir.mkdir(parents=True, exist_ok=True)

        bbmd_config = generate_bbmd_config(
            i,
            num_buildings,
            expose_bacnet=args.expose_bacnet,
            peer_entries=get_scenario_bdt_peer_overrides(i, args.scenario),
        )
        (bbmd_dir / "bbmd_config.yaml").write_text(bbmd_config)

        acl_config = generate_acl_config()
        (bbmd_dir / "acl_rules.yaml").write_text(acl_config)

        print(f"  Written: {bbmd_dir}/bbmd_config.yaml")
        print(f"  Written: {bbmd_dir}/acl_rules.yaml")

    # Generate docker-compose.campus.yml
    compose_content = generate_compose(
        campus,
        str(ttl_path),
        expose_bacnet=args.expose_bacnet,
        scenario=args.scenario,
    )
    compose_path = PROJECT_ROOT / "docker-compose.campus.yml"
    compose_path.write_text(compose_content)
    print(f"\nWritten: {compose_path}")

    if args.expose_bacnet:
        print("External BACnet exposure: enabled")
    else:
        print("External BACnet exposure: disabled (use --expose-bacnet to publish BBMD ports)")

    print(
        f"\nCampus generation complete: {num_buildings} buildings, "
        f"{num_buildings} BBMDs, {num_buildings} simulators"
    )
    print("\nTo start: podman-compose -f docker-compose.campus.yml up")


if __name__ == "__main__":
    main()

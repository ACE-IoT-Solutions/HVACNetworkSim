#!/usr/bin/env python3
"""
Campus Compose Generator - Generate docker-compose and BBMD configs from a campus TTL file.

Parses a Brick schema campus TTL file and generates:
- docker-compose.campus.yml with per-building networks, BBMD and sim services
- campus/configs/bbmd{N}/bbmd_config.yaml and acl_rules.yaml per building

Network architecture (example with 2 buildings):

    Building 1 Network (10.1.0.0/24)       Building 2 Network (10.2.0.0/24)
    ├── BBMD1 (10.1.0.2/24:47808)          ├── BBMD2 (10.2.0.2/24:47808)
    ├── Sim1 (10.1.0.10)                   ├── Sim2 (10.2.0.10)
    └── Router (10.1.0.254)                └── Router (10.2.0.254)

    BBMDs peer via direct IP routing through the campus router:
    BBMD1 BDT: self (10.1.0.2/24) + peer (10.2.0.2/24)
    BBMD2 BDT: self (10.2.0.2/24) + peer (10.1.0.2/24)

    Campus router enables IP routing between building subnets.
    All containers (sims + BBMDs) have static routes via the router.
    Host port mapping retained for external scanner access.

Usage:
    python campus/generate_campus.py examples/multi_building_campus.ttl
    python campus/generate_campus.py examples/large_campus.ttl
"""

import sys
from pathlib import Path

# Add project root to path so we can import src modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def parse_campus(ttl_file: str):
    """Parse a campus TTL file and return the CampusStructure."""
    from src.brick.parser import BrickParser

    parser = BrickParser(ttl_file)
    return parser.extract_all_buildings()


# Base host port for BBMD port mapping (external access): building i gets port BASE + i
BBMD_HOST_PORT_BASE = 47808


def generate_bbmd_config(building_index: int, num_buildings: int) -> str:
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
    building_ip = f"10.{building_index}.0.2"

    # BDT must include self (required for local rebroadcast of forwarded packets)
    # and all peer BBMDs via their real building subnet addresses.
    # Self uses /24 mask (for correct local subnet broadcast).
    # Peers use /32 mask (unicast to peer - directed broadcasts don't route across subnets).
    bdt_lines = [f'  - "{building_ip}/24:47808"']  # Self entry with subnet mask
    for i in range(1, num_buildings + 1):
        if i != building_index:
            peer_ip = f"10.{i}.0.2"
            bdt_lines.append(f'  - "{peer_ip}/32:47808"')  # Peer entry with host mask (unicast)
    bdt_entries = "\n".join(bdt_lines)

    # BBMD device ID must be unique across the BACnet internetwork.
    # Router for building N is at N*1000-1 (999, 1999, ...), equipment starts at N*1000.
    # Place BBMD at N*1000-2 (998, 1998, ...) to avoid collisions.
    bbmd_device_id = building_index * 1000 - 2

    return f"""bbmd_address: "{building_ip}/24:47808"
device_id: {bbmd_device_id}
bdt_entries:
{bdt_entries}
accept_foreign_devices: true
log_level: "INFO"
enable_metrics: true
metrics_http_port: 9090
"""


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


def generate_compose(campus, ttl_file: str, bbmd_image: str = "ace-acl-bbmd") -> str:
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
        "",
        "networks:",
    ]

    # Building networks (BBMDs peer via direct IP routing through campus router)
    for i in range(1, num_buildings + 1):
        lines.extend(
            [
                f"  building{i}:",
                "    driver: bridge",
                "    ipam:",
                "      config:",
                f"        - subnet: 10.{i}.0.0/24",
            ]
        )

    lines.extend(["", "services:"])

    # Generate services for each building
    for i, (building_name, building) in enumerate(buildings, 1):
        building_ip = f"10.{i}.0.2"
        sim_ip = f"10.{i}.0.10"
        host_port = BBMD_HOST_PORT_BASE + i
        safe_name = building_name.lower().replace(" ", "_").replace("-", "_")

        # Build route-add commands for the BBMD to reach other building subnets
        bbmd_route_cmds = []
        for j in range(1, num_buildings + 1):
            if j != i:
                bbmd_route_cmds.append(
                    f"ip route add 10.{j}.0.0/24 via 10.{i}.0.254 2>/dev/null || true"
                )

        # BBMD service - on building network, with routes to peer subnets
        lines.extend(
            [
                f"  bbmd{i}:",
                f"    image: {bbmd_image}",
                f"    container_name: campus-bbmd{i}",
                "    networks:",
                f"      building{i}:",
                f"        ipv4_address: {building_ip}",
                "    ports:",
                f'      - "{host_port}:47808/udp"',
                "    volumes:",
                f"      - ./campus/configs/bbmd{i}/bbmd_config.yaml:/app/config/bbmd_config.yaml:ro",
                f"      - ./campus/configs/bbmd{i}/acl_rules.yaml:/app/config/acl_rules.yaml:ro",
            ]
        )
        if bbmd_route_cmds and num_buildings > 1:
            # Wrap the default CMD with route setup
            route_str = " && ".join(bbmd_route_cmds)
            lines.extend(
                [
                    "    cap_add:",
                    "      - NET_ADMIN",
                    '    entrypoint: ["/bin/sh", "-c"]',
                    f'    command: ["{route_str} && exec ace-acl-bbmd --config /app/config/bbmd_config.yaml --acl /app/config/acl_rules.yaml"]',
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
        # via the router at 10.{this_building}.0.254
        routes = []
        for j in range(1, num_buildings + 1):
            if j != i:
                routes.append(f"10.{j}.0.0/24:10.{i}.0.254")
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
            f"      - ./{ttl_relative.parent}:/app/brick_schemas:ro",
            "    environment:",
            "      - SIMULATION_MODE=brick",
            f"      - BRICK_TTL_FILE=/app/brick_schemas/{ttl_relative.name}",
            f"      - BUILDING_NAME={building_name}",
            "      - BACNET_SUBNET=24",
        ]
        if campus_routes:
            sim_lines.append(f"      - CAMPUS_ROUTES={campus_routes}")
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
                    f"        ipv4_address: 10.{i}.0.254",
                ]
            )
        lines.extend(
            [
                "    cap_add:",
                "      - NET_ADMIN",
                "    sysctls:",
                "      - net.ipv4.ip_forward=1",
                '    entrypoint: ["/bin/sh", "-c"]',
            ]
        )

        # ip_forward=1 via sysctl handles forwarding; no iptables needed in alpine
        router_cmds = []
        for i in range(1, num_buildings + 1):
            router_cmds.append(f"echo 'Connected to building{i}: 10.{i}.0.0/24'")
        router_cmds.append("echo 'IP forwarding enabled, campus router ready'")
        router_cmds.append("sleep infinity")

        cmd_str = " && ".join(router_cmds)
        lines.extend(
            [
                f'    command: ["{cmd_str}"]',
                "    restart: unless-stopped",
                "",
            ]
        )

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python campus/generate_campus.py <ttl_file>", file=sys.stderr)
        print(
            "Example: python campus/generate_campus.py examples/multi_building_campus.ttl",
            file=sys.stderr,
        )
        sys.exit(1)

    ttl_file = sys.argv[1]
    ttl_path = Path(ttl_file)

    # Resolve relative to project root if not absolute
    if not ttl_path.is_absolute():
        ttl_path = PROJECT_ROOT / ttl_path

    if not ttl_path.exists():
        print(f"Error: TTL file not found: {ttl_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing campus TTL: {ttl_path}")
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

        bbmd_config = generate_bbmd_config(i, num_buildings)
        (bbmd_dir / "bbmd_config.yaml").write_text(bbmd_config)

        acl_config = generate_acl_config()
        (bbmd_dir / "acl_rules.yaml").write_text(acl_config)

        print(f"  Written: {bbmd_dir}/bbmd_config.yaml")
        print(f"  Written: {bbmd_dir}/acl_rules.yaml")

    # Generate docker-compose.campus.yml
    compose_content = generate_compose(campus, str(ttl_path))
    compose_path = PROJECT_ROOT / "docker-compose.campus.yml"
    compose_path.write_text(compose_content)
    print(f"\nWritten: {compose_path}")

    print(
        f"\nCampus generation complete: {num_buildings} buildings, "
        f"{num_buildings} BBMDs, {num_buildings} simulators"
    )
    print("\nTo start: podman-compose -f docker-compose.campus.yml up")


if __name__ == "__main__":
    main()

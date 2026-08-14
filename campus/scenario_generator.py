"""Generate scalable Brick campus scenarios for HVACNetwork."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BUILDINGS = 2
DEFAULT_TERMINAL_UNITS = 10
TERMINAL_UNITS_PER_AHU = 10
TERMINAL_UNITS_PER_PLANT = 50
MAX_BUILDINGS = 64
MAX_TERMINAL_UNITS_PER_BUILDING = 90


@dataclass(frozen=True)
class ScenarioSize:
    """Calculated equipment quantities for one generated building."""

    terminal_units: int
    ahus: int
    chillers: int
    boilers: int
    cooling_towers: int


def calculate_scenario_size(terminal_units: int) -> ScenarioSize:
    """Derive air-side and plant equipment from a terminal-unit count."""

    if not 1 <= terminal_units <= MAX_TERMINAL_UNITS_PER_BUILDING:
        raise ValueError(f"terminal units must be between 1 and {MAX_TERMINAL_UNITS_PER_BUILDING}")

    ahus = math.ceil(terminal_units / TERMINAL_UNITS_PER_AHU)
    plant_units = math.ceil(terminal_units / TERMINAL_UNITS_PER_PLANT)
    return ScenarioSize(
        terminal_units=terminal_units,
        ahus=ahus,
        chillers=plant_units,
        boilers=plant_units,
        cooling_towers=plant_units,
    )


def _resource_list(resources: list[str], indent: str = "        ") -> str:
    """Format a Turtle resource list with readable continuation indentation."""

    return (",\n" + indent).join(f"scenario:{resource}" for resource in resources)


def _render_building(building_index: int, size: ScenarioSize, multi_network: bool) -> str:
    building = f"Building{building_index}"
    area = size.terminal_units * 400
    lines = [
        "# " + "=" * 76,
        f"# {building}: {size.terminal_units} terminal units, {size.ahus} AHUs",
        "# " + "=" * 76,
        "",
        f"scenario:{building} a brick:Building ;",
        f'    rdfs:label "Building {building_index}" ;',
        "    brick:area [ brick:hasUnits unit:FT_2 ;",
        f'            brick:value "{area}" ]' + (" ;" if multi_network else " ."),
    ]
    if multi_network:
        lines.extend(
            [
                f"    bacnet:networkNumber {building_index * 100} ;",
                f'    scenario:ipSubnet "10.{building_index}.0.0/24" .',
            ]
        )
    lines.append("")

    chillers = [f"{building}_Chiller{i:02d}" for i in range(1, size.chillers + 1)]
    boilers = [f"{building}_Boiler{i:02d}" for i in range(1, size.boilers + 1)]

    for ahu_index in range(1, size.ahus + 1):
        start = (ahu_index - 1) * TERMINAL_UNITS_PER_AHU + 1
        end = min(ahu_index * TERMINAL_UNITS_PER_AHU, size.terminal_units)
        terminals = [f"{building}_VAV{i:03d}" for i in range(start, end + 1)]
        plant_index = min(
            (start - 1) // TERMINAL_UNITS_PER_PLANT,
            size.chillers - 1,
        )
        lines.extend(
            [
                f"scenario:{building}_AHU{ahu_index:02d} a brick:Air_Handler_Unit ;",
                f"    brick:isPartOf scenario:{building} ;",
                f"    brick:feeds {_resource_list(terminals)} ;",
                f"    brick:isFedBy scenario:{chillers[plant_index]},",
                f"        scenario:{boilers[plant_index]} .",
                "",
            ]
        )

    for terminal_index in range(1, size.terminal_units + 1):
        vav = f"{building}_VAV{terminal_index:03d}"
        zone = f"{building}_Zone{terminal_index:03d}"
        room = f"{building}_Room{terminal_index:03d}"
        point_base = f"{vav}_"
        lines.extend(
            [
                f"scenario:{vav} a brick:VAV ;",
                f"    brick:isPartOf scenario:{building} ;",
                f"    brick:feeds scenario:{zone} ;",
                f"    brick:hasPoint scenario:{point_base}ZAT,",
                f"        scenario:{point_base}ZAT_SP,",
                f"        scenario:{point_base}DAM,",
                f"        scenario:{point_base}SAF,",
                f"        scenario:{point_base}RHV .",
                "",
                f"scenario:{point_base}ZAT a brick:Zone_Air_Temperature_Sensor ;",
                f'    rdfs:label "{building}.VAV{terminal_index:03d}.Zone Air Temp" .',
                f"scenario:{point_base}ZAT_SP a brick:Zone_Air_Temperature_Setpoint ;",
                f'    rdfs:label "{building}.VAV{terminal_index:03d}.Zone Air Temp Setpoint" .',
                f"scenario:{point_base}DAM a brick:Damper_Position_Setpoint ;",
                f'    rdfs:label "{building}.VAV{terminal_index:03d}.Damper Command" .',
                f"scenario:{point_base}SAF a brick:Supply_Air_Flow_Sensor ;",
                f'    rdfs:label "{building}.VAV{terminal_index:03d}.Supply Air Flow" .',
                f"scenario:{point_base}RHV a brick:Reheat_Valve_Command ;",
                f'    rdfs:label "{building}.VAV{terminal_index:03d}.Reheat Valve Command" .',
                "",
                f"scenario:{zone} a brick:HVAC_Zone ;",
                f"    brick:isPartOf scenario:{building} ;",
                f"    brick:hasPart scenario:{room} .",
                f"scenario:{room} a brick:Room .",
                "",
            ]
        )

    for plant_index in range(1, size.chillers + 1):
        chiller = f"{building}_Chiller{plant_index:02d}"
        tower = f"{building}_CoolingTower{plant_index:02d}"
        lines.extend(
            [
                f"scenario:{chiller} a brick:Chiller ;",
                f"    brick:isPartOf scenario:{building} ;",
                f"    brick:isFedBy scenario:{tower} .",
                f"scenario:{tower} a brick:Cooling_Tower ;",
                f"    brick:isPartOf scenario:{building} ;",
                f"    brick:feeds scenario:{chiller} .",
                "",
            ]
        )

    for plant_index in range(1, size.boilers + 1):
        lines.extend(
            [
                f"scenario:{building}_Boiler{plant_index:02d} a brick:Boiler ;",
                f"    brick:isPartOf scenario:{building} .",
                "",
            ]
        )

    return "\n".join(lines)


def generate_scenario(buildings: int, terminal_units: int, multi_network: bool = False) -> str:
    """Return a generated Brick campus scenario as Turtle text."""

    if not 1 <= buildings <= MAX_BUILDINGS:
        raise ValueError(f"buildings must be between 1 and {MAX_BUILDINGS}")
    size = calculate_scenario_size(terminal_units)

    header = [
        "@prefix bacnet: <http://data.ashrae.org/bacnet/2020#> .",
        "@prefix brick: <https://brickschema.org/schema/Brick#> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix scenario: <urn:hvac-sim:scenario#> .",
        "@prefix unit: <http://qudt.org/vocab/unit/> .",
        "",
        "<urn:hvac-sim:generated-scenario> a owl:Ontology ;",
        '    rdfs:label "Generated HVAC Simulation Scenario" ;',
        "    owl:imports <https://brickschema.org/schema/1.4/Brick> .",
        "",
        "# Generated by hvac-sim. Equipment sizing defaults:",
        f"# - 1 AHU per {TERMINAL_UNITS_PER_AHU} terminal units",
        f"# - 1 chiller and boiler per {TERMINAL_UNITS_PER_PLANT} terminal units",
        "# - 1 cooling tower per chiller",
        f"# - Network mode: {'one subnet per building' if multi_network else 'single network'}",
        "",
    ]
    sections = [_render_building(i, size, multi_network) for i in range(1, buildings + 1)]
    return "\n".join(header + sections).rstrip() + "\n"


def write_scenario(
    output: str | Path,
    buildings: int,
    terminal_units: int,
    multi_network: bool = False,
    force: bool = False,
) -> tuple[Path, ScenarioSize]:
    """Generate a scenario and write it to a new TTL file."""

    output_path = Path(output).expanduser().resolve()
    if output_path.suffix.lower() != ".ttl":
        raise ValueError("scenario output must use the .ttl extension")
    if output_path.exists() and not force:
        raise FileExistsError(f"scenario already exists: {output_path} (use --force to replace it)")

    content = generate_scenario(buildings, terminal_units, multi_network)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path, calculate_scenario_size(terminal_units)

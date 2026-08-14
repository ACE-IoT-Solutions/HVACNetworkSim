"""Tests for scalable Brick scenario generation."""

from pathlib import Path

import pytest
from rdflib import Graph, Namespace
from rdflib.namespace import RDF

from campus.generate_campus import generate_compose
from campus.scenario_generator import calculate_scenario_size, generate_scenario, write_scenario
from src.brick.parser import BrickParser


BRICK = Namespace("https://brickschema.org/schema/Brick#")
BACNET = Namespace("http://data.ashrae.org/bacnet/2020#")
SCENARIO = Namespace("urn:hvac-sim:scenario#")


def test_equipment_defaults_round_up_from_terminal_units():
    size = calculate_scenario_size(51)

    assert size.terminal_units == 51
    assert size.ahus == 6
    assert size.chillers == 2
    assert size.boilers == 2
    assert size.cooling_towers == 2


def test_generated_scenario_has_requested_topology():
    graph = Graph().parse(data=generate_scenario(3, 12), format="turtle")

    assert len(set(graph.subjects(RDF.type, BRICK.Building))) == 3
    assert len(set(graph.subjects(RDF.type, BRICK.VAV))) == 36
    assert len(set(graph.subjects(RDF.type, BRICK.Air_Handler_Unit))) == 6
    assert len(set(graph.subjects(RDF.type, BRICK.Chiller))) == 3
    assert len(set(graph.subjects(RDF.type, BRICK.Boiler))) == 3
    assert len(set(graph.subjects(RDF.type, BRICK.Cooling_Tower))) == 3


def test_multi_network_annotations_are_parsed_and_used_by_campus(tmp_path: Path):
    ttl_path = tmp_path / "campus.ttl"
    ttl_path.write_text(generate_scenario(2, 3, multi_network=True), encoding="utf-8")

    campus = BrickParser(str(ttl_path)).extract_all_buildings()
    building1 = campus.get_building("Building1")
    building2 = campus.get_building("Building2")

    assert building1 is not None
    assert building1.network_number == 100
    assert building1.ip_subnet == "10.1.0.0/24"
    assert building2 is not None
    assert building2.network_number == 200
    assert building2.ip_subnet == "10.2.0.0/24"

    compose = generate_compose(campus, str(ttl_path))
    assert 'BACNET_NETWORK_NUMBER: "100"' in compose
    assert 'BACNET_NETWORK_NUMBER: "200"' in compose


def test_single_network_scenario_omits_network_annotations():
    graph = Graph().parse(data=generate_scenario(2, 2), format="turtle")

    building1 = SCENARIO.Building1
    assert list(graph.objects(building1, BACNET.networkNumber)) == []
    assert list(graph.objects(building1, SCENARIO.ipSubnet)) == []


def test_write_scenario_refuses_overwrite_without_force(tmp_path: Path):
    output = tmp_path / "scenario.ttl"
    write_scenario(output, 1, 1)

    with pytest.raises(FileExistsError):
        write_scenario(output, 1, 1)

    write_scenario(output, 1, 2, force=True)
    campus = BrickParser(str(output)).extract_all_buildings()
    assert len(campus.get_building("Building1").vavs) == 2  # type: ignore[union-attr]


@pytest.mark.parametrize("buildings,terminals", [(0, 1), (65, 1), (1, 0), (1, 91)])
def test_invalid_sizes_are_rejected(buildings: int, terminals: int):
    with pytest.raises(ValueError):
        generate_scenario(buildings, terminals)

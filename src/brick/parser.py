"""Brick schema parser for extracting building topology.

This module parses Brick TTL files to extract equipment relationships
for building the simulation model.
"""

import re
from typing import Any

try:
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF, RDFS

    RDFLIB_AVAILABLE = True
except ImportError:
    RDFLIB_AVAILABLE = False
    Graph = None  # type: ignore
    Namespace = None  # type: ignore
    RDF = None  # type: ignore
    RDFS = None  # type: ignore


class BrickParser:
    """Parser for BRICK schema files to extract building structure."""

    def __init__(self, file_path: str):
        """Initialize the BRICK parser.

        Args:
            file_path: Path to the BRICK TTL file

        Raises:
            ImportError: If rdflib is not available
        """
        if not RDFLIB_AVAILABLE:
            raise ImportError(
                "rdflib is required to parse BRICK schema files. "
                "Install with: pip install rdflib"
            )

        self.file_path = file_path
        self.graph = Graph()
        self.g = self.graph  # Alias for shorter access

        # Load the TTL file
        self.g.parse(file_path, format="turtle")

        # Define namespaces
        self.BRICK = Namespace("https://brickschema.org/schema/Brick#")
        self.REF = Namespace("https://brickschema.org/schema/Brick/ref#")

        # Try to extract the main namespace from the file
        self.main_ns = None
        for prefix, uri in self.g.namespaces():
            if prefix in ("ns1", "ns2", "ns3", "ns4") or prefix == "":
                self.main_ns = Namespace(uri)
                break

        if not self.main_ns:
            # Fallback to a default namespace
            self.main_ns = Namespace("http://buildsys.org/ontologies/bldg1#")

        # Bind namespaces for queries
        self.g.bind("brick", self.BRICK)
        self.g.bind("ref", self.REF)
        self.g.bind("main", self.main_ns)

    def extract_building_info(self) -> dict[str, Any]:
        """Extract basic building information.

        Returns:
            Dictionary with building name and area if available
        """
        building_info: dict[str, Any] = {}

        # Find building instance
        for building in self.g.subjects(RDF.type, self.BRICK.Building):
            # Get building name
            for name in self.g.objects(building, RDFS.label):
                building_info["name"] = str(name)
                break

            # Get building area
            for area_node in self.g.objects(building, self.BRICK.area):
                for value in self.g.objects(area_node, self.BRICK.value):
                    # Extract numeric value from the string
                    match = re.search(r"(\d+)", str(value))
                    if match:
                        building_info["area"] = int(match.group(1))
                        break

            # Only process the first building found
            break

        return building_info

    def extract_ahu_info(self) -> dict[str, dict[str, Any]]:
        """Extract AHU information and their relationships.

        Returns:
            Dictionary mapping AHU IDs to their configuration
        """
        ahu_info: dict[str, dict[str, Any]] = {}

        # Look for both AHU and Air_Handler_Unit types (Brick schema variants)
        ahu_types = [self.BRICK.AHU, self.BRICK.Air_Handler_Unit]
        ahu_subjects = set()
        for ahu_type in ahu_types:
            for ahu in self.g.subjects(RDF.type, ahu_type):
                ahu_subjects.add(ahu)

        for ahu in ahu_subjects:
            ahu_id = str(ahu).split("#")[-1]

            # Initialize AHU entry
            ahu_info[ahu_id] = {"id": ahu_id, "feeds": [], "points": [], "fed_by": []}

            # Get VAV boxes fed by this AHU
            for vav in self.g.objects(ahu, self.BRICK.feeds):
                vav_id = str(vav).split("#")[-1]
                ahu_info[ahu_id]["feeds"].append(vav_id)

            # Get data points related to this AHU
            for point in self.g.objects(ahu, self.BRICK.hasPoint):
                point_id = str(point).split("#")[-1]
                ahu_info[ahu_id]["points"].append(point_id)

                # Get point type
                for point_type in self.g.objects(point, RDF.type):
                    if "Temperature" in str(point_type):
                        temp_type = str(point_type).split("#")[-1]
                        ahu_info[ahu_id][temp_type] = point_id

            # Get equipment feeding this AHU
            for source in self.g.objects(ahu, self.BRICK.isFedBy):
                source_id = str(source).split("#")[-1]
                ahu_info[ahu_id]["fed_by"].append(source_id)

        return ahu_info

    def extract_vav_info(self) -> dict[str, dict[str, Any]]:
        """Extract VAV box information and their relationships.

        Returns:
            Dictionary mapping VAV IDs to their configuration
        """
        vav_info: dict[str, dict[str, Any]] = {}

        for vav in self.g.subjects(RDF.type, self.BRICK.VAV):
            vav_id = str(vav).split("#")[-1]

            # Initialize VAV entry
            vav_info[vav_id] = {
                "id": vav_id,
                "feeds": [],
                "points": [],
                "has_reheat": False,
            }

            # Get zones fed by this VAV
            for zone in self.g.objects(vav, self.BRICK.feeds):
                zone_id = str(zone).split("#")[-1]
                vav_info[vav_id]["feeds"].append(zone_id)

            # Get data points related to this VAV
            for point in self.g.objects(vav, self.BRICK.hasPoint):
                point_id = str(point).split("#")[-1]
                point_label = None

                # Try to get point label
                for label in self.g.objects(point, RDFS.label):
                    point_label = str(label)
                    break

                # Get point type
                point_info = {"id": point_id, "label": point_label, "types": []}
                for point_type in self.g.objects(point, RDF.type):
                    type_name = str(point_type).split("#")[-1]
                    point_info["types"].append(type_name)

                    # Check for reheat
                    if "Reheat" in type_name or ("Valve" in type_name and "Heat" in type_name):
                        vav_info[vav_id]["has_reheat"] = True

                vav_info[vav_id]["points"].append(point_info)

                # Categorize specific point types for easier access
                if point_label:
                    lower_label = point_label.lower()

                    if "zone air temp" in lower_label and "setpoint" not in lower_label:
                        vav_info[vav_id]["zone_temp_sensor"] = point_id
                    elif "setpoint" in lower_label:
                        vav_info[vav_id]["temp_setpoint"] = point_id
                    elif "damper" in lower_label:
                        vav_info[vav_id]["damper_command"] = point_id
                    elif "reheat" in lower_label:
                        vav_info[vav_id]["reheat_command"] = point_id
                        vav_info[vav_id]["has_reheat"] = True
                    elif "air flow" in lower_label:
                        vav_info[vav_id]["airflow_sensor"] = point_id

        return vav_info

    def extract_zone_info(self) -> dict[str, dict[str, Any]]:
        """Extract zone information and their relationships.

        Returns:
            Dictionary mapping zone IDs to their configuration
        """
        zone_info: dict[str, dict[str, Any]] = {}

        for zone in self.g.subjects(RDF.type, self.BRICK.HVAC_Zone):
            zone_id = str(zone).split("#")[-1]

            # Initialize zone entry
            zone_info[zone_id] = {"id": zone_id, "rooms": []}

            # Get rooms in this zone
            for room in self.g.objects(zone, self.BRICK.hasPart):
                room_id = str(room).split("#")[-1]
                zone_info[zone_id]["rooms"].append(room_id)

        return zone_info

    def extract_chiller_info(self) -> dict[str, dict[str, Any]]:
        """Extract chiller information and their relationships.

        Returns:
            Dictionary mapping chiller IDs to their configuration
        """
        chiller_info: dict[str, dict[str, Any]] = {}

        for chiller in self.g.subjects(RDF.type, self.BRICK.Chiller):
            chiller_id = str(chiller).split("#")[-1]

            # Initialize chiller entry
            chiller_info[chiller_id] = {"id": chiller_id, "points": []}

            # Get data points related to this chiller
            for point in self.g.objects(chiller, self.BRICK.hasPoint):
                point_id = str(point).split("#")[-1]
                point_label = None

                # Try to get point label
                for label in self.g.objects(point, RDFS.label):
                    point_label = str(label)
                    break

                point_info = {"id": point_id, "label": point_label, "types": []}

                # Get point type
                for point_type in self.g.objects(point, RDF.type):
                    type_name = str(point_type).split("#")[-1]
                    point_info["types"].append(type_name)

                chiller_info[chiller_id]["points"].append(point_info)

                # Categorize specific point types
                if point_label:
                    lower_label = point_label.lower()
                    if "supply temp" in lower_label:
                        chiller_info[chiller_id]["supply_temp_sensor"] = point_id
                    elif "return temp" in lower_label:
                        chiller_info[chiller_id]["return_temp_sensor"] = point_id

        return chiller_info

    def extract_boiler_info(self) -> dict[str, dict[str, Any]]:
        """Extract boiler information and their relationships.

        Returns:
            Dictionary mapping boiler IDs to their configuration
        """
        boiler_info: dict[str, dict[str, Any]] = {}

        for boiler in self.g.subjects(RDF.type, self.BRICK.Boiler):
            boiler_id = str(boiler).split("#")[-1]
            boiler_info[boiler_id] = {"id": boiler_id, "points": []}

            # Get data points related to this boiler
            for point in self.g.objects(boiler, self.BRICK.hasPoint):
                point_id = str(point).split("#")[-1]
                point_label = None

                for label in self.g.objects(point, RDFS.label):
                    point_label = str(label)
                    break

                point_info = {"id": point_id, "label": point_label, "types": []}
                for point_type in self.g.objects(point, RDF.type):
                    type_name = str(point_type).split("#")[-1]
                    point_info["types"].append(type_name)

                boiler_info[boiler_id]["points"].append(point_info)

        return boiler_info

    def extract_all_equipment(self) -> dict[str, Any]:
        """Extract all equipment information from the BRICK schema.

        Returns:
            Dictionary containing all building equipment structure
        """
        building_info = self.extract_building_info()
        ahu_info = self.extract_ahu_info()
        vav_info = self.extract_vav_info()
        zone_info = self.extract_zone_info()
        chiller_info = self.extract_chiller_info()
        boiler_info = self.extract_boiler_info()

        return {
            "building": building_info,
            "ahus": ahu_info,
            "vavs": vav_info,
            "zones": zone_info,
            "chillers": chiller_info,
            "boilers": boiler_info,
        }

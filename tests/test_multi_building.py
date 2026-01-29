"""Tests for multi-building campus parsing functionality."""

import os
import unittest

from src.brick.campus import BuildingStructure, CampusStructure
from src.brick.parser import BrickParser


class TestBuildingStructure(unittest.TestCase):
    """Tests for BuildingStructure dataclass."""

    def test_initialization(self):
        """Test BuildingStructure initializes with correct defaults."""
        building = BuildingStructure(name="TestBuilding")

        self.assertEqual(building.name, "TestBuilding")
        self.assertIsNone(building.area)
        self.assertEqual(building.ahus, {})
        self.assertEqual(building.vavs, {})
        self.assertEqual(building.zones, {})
        self.assertEqual(building.chillers, {})
        self.assertEqual(building.boilers, {})
        self.assertEqual(building.cooling_towers, [])

    def test_initialization_with_values(self):
        """Test BuildingStructure initializes with provided values."""
        building = BuildingStructure(
            name="OfficeBuilding",
            area=15000,
            ahus={"AHU1": {"id": "AHU1"}},
            vavs={"VAV1": {"id": "VAV1"}, "VAV2": {"id": "VAV2"}},
            chillers={"Chiller1": {"id": "Chiller1"}},
        )

        self.assertEqual(building.name, "OfficeBuilding")
        self.assertEqual(building.area, 15000)
        self.assertEqual(len(building.ahus), 1)
        self.assertEqual(len(building.vavs), 2)
        self.assertEqual(len(building.chillers), 1)

    def test_get_equipment_summary(self):
        """Test equipment summary calculation."""
        building = BuildingStructure(
            name="TestBuilding",
            ahus={"AHU1": {}, "AHU2": {}},
            vavs={"VAV1": {}, "VAV2": {}, "VAV3": {}},
            chillers={"Chiller1": {}},
        )

        summary = building.get_equipment_summary()

        self.assertEqual(summary["ahus"], 2)
        self.assertEqual(summary["vavs"], 3)
        self.assertEqual(summary["chillers"], 1)
        self.assertEqual(summary["boilers"], 0)
        self.assertEqual(summary["zones"], 0)
        self.assertEqual(summary["cooling_towers"], 0)

    def test_has_central_plant(self):
        """Test central plant detection."""
        # Building with chiller
        building_with_chiller = BuildingStructure(name="Building1", chillers={"Chiller1": {}})
        self.assertTrue(building_with_chiller.has_central_plant())

        # Building with boiler
        building_with_boiler = BuildingStructure(name="Building2", boilers={"Boiler1": {}})
        self.assertTrue(building_with_boiler.has_central_plant())

        # Building without central plant
        building_no_plant = BuildingStructure(
            name="Building3", ahus={"AHU1": {}}, vavs={"VAV1": {}}
        )
        self.assertFalse(building_no_plant.has_central_plant())


class TestCampusStructure(unittest.TestCase):
    """Tests for CampusStructure dataclass."""

    def test_initialization(self):
        """Test CampusStructure initializes with correct defaults."""
        campus = CampusStructure()

        self.assertEqual(campus.name, "Campus")
        self.assertEqual(campus.buildings, {})

    def test_add_building(self):
        """Test adding buildings to campus."""
        campus = CampusStructure(name="TestCampus")

        building1 = BuildingStructure(name="Building1", area=10000)
        building2 = BuildingStructure(name="Building2", area=15000)

        campus.add_building(building1)
        campus.add_building(building2)

        self.assertEqual(len(campus.buildings), 2)
        self.assertIn("Building1", campus.buildings)
        self.assertIn("Building2", campus.buildings)

    def test_get_building(self):
        """Test retrieving building by name."""
        campus = CampusStructure()
        building = BuildingStructure(name="MainBuilding", area=20000)
        campus.add_building(building)

        retrieved = campus.get_building("MainBuilding")
        self.assertEqual(retrieved.name, "MainBuilding")
        self.assertEqual(retrieved.area, 20000)

        # Non-existent building
        self.assertIsNone(campus.get_building("NonExistent"))

    def test_get_all_equipment_count(self):
        """Test total equipment count across all buildings."""
        campus = CampusStructure()

        building1 = BuildingStructure(
            name="Building1",
            ahus={"AHU1": {}},
            vavs={"VAV1": {}, "VAV2": {}},
            chillers={"Chiller1": {}},
        )

        building2 = BuildingStructure(
            name="Building2",
            ahus={"AHU2": {}},
            vavs={"VAV3": {}, "VAV4": {}, "VAV5": {}},
            boilers={"Boiler1": {}},
        )

        campus.add_building(building1)
        campus.add_building(building2)

        totals = campus.get_all_equipment_count()

        self.assertEqual(totals["buildings"], 2)
        self.assertEqual(totals["ahus"], 2)
        self.assertEqual(totals["vavs"], 5)
        self.assertEqual(totals["chillers"], 1)
        self.assertEqual(totals["boilers"], 1)

    def test_is_multi_building(self):
        """Test multi-building detection."""
        campus = CampusStructure()

        # Empty campus
        self.assertFalse(campus.is_multi_building())

        # Single building
        campus.add_building(BuildingStructure(name="Building1"))
        self.assertFalse(campus.is_multi_building())

        # Multiple buildings
        campus.add_building(BuildingStructure(name="Building2"))
        self.assertTrue(campus.is_multi_building())


class TestBrickParserMultiBuilding(unittest.TestCase):
    """Tests for multi-building parsing in BrickParser."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        # Path to the multi-building example TTL
        cls.multi_building_ttl = os.path.join(
            os.path.dirname(__file__),
            "..",
            "examples",
            "multi_building_campus.ttl",
        )

        # Path to a single-building TTL for comparison
        cls.single_building_ttl = os.path.join(
            os.path.dirname(__file__),
            "..",
            "data",
            "brick_schemas",
            "bldg1.ttl",
        )

    def test_extract_all_buildings_multi_building(self):
        """Test extracting multiple buildings from campus TTL."""
        if not os.path.exists(self.multi_building_ttl):
            self.skipTest("Multi-building TTL not found")

        parser = BrickParser(self.multi_building_ttl)
        campus = parser.extract_all_buildings()

        # Should have 2 buildings
        self.assertEqual(len(campus.buildings), 2)
        self.assertTrue(campus.is_multi_building())

        # Check Building1
        building1 = campus.get_building("Building1")
        self.assertIsNotNone(building1)
        self.assertEqual(building1.area, 15000)
        self.assertEqual(len(building1.ahus), 1)
        self.assertEqual(len(building1.vavs), 4)
        self.assertEqual(len(building1.chillers), 1)
        self.assertEqual(len(building1.boilers), 0)

        # Check Building2
        building2 = campus.get_building("Building2")
        self.assertIsNotNone(building2)
        self.assertEqual(building2.area, 12000)
        self.assertEqual(len(building2.ahus), 1)
        self.assertEqual(len(building2.vavs), 3)
        self.assertEqual(len(building2.chillers), 0)
        self.assertEqual(len(building2.boilers), 1)

    def test_extract_all_buildings_single_building(self):
        """Test extracting buildings from single-building TTL."""
        if not os.path.exists(self.single_building_ttl):
            self.skipTest("Single-building TTL not found")

        parser = BrickParser(self.single_building_ttl)
        campus = parser.extract_all_buildings()

        # Should have at least 1 building
        self.assertGreaterEqual(len(campus.buildings), 1)

        # Get first building
        building = list(campus.buildings.values())[0]

        # Should have equipment
        self.assertGreater(len(building.ahus), 0)
        self.assertGreater(len(building.vavs), 0)

    def test_campus_equipment_totals(self):
        """Test that campus equipment totals are correct."""
        if not os.path.exists(self.multi_building_ttl):
            self.skipTest("Multi-building TTL not found")

        parser = BrickParser(self.multi_building_ttl)
        campus = parser.extract_all_buildings()

        totals = campus.get_all_equipment_count()

        # Total equipment across both buildings
        self.assertEqual(totals["buildings"], 2)
        self.assertEqual(totals["ahus"], 2)  # 1 per building
        self.assertEqual(totals["vavs"], 7)  # 4 + 3
        self.assertEqual(totals["chillers"], 1)  # Only in Building1
        self.assertEqual(totals["boilers"], 1)  # Only in Building2

    def test_building_equipment_isolation(self):
        """Test that equipment is correctly isolated to their buildings."""
        if not os.path.exists(self.multi_building_ttl):
            self.skipTest("Multi-building TTL not found")

        parser = BrickParser(self.multi_building_ttl)
        campus = parser.extract_all_buildings()

        building1 = campus.get_building("Building1")
        building2 = campus.get_building("Building2")

        # Building1 should only have its own equipment
        for vav_id in building1.vavs:
            self.assertIn("Building1", vav_id)

        # Building2 should only have its own equipment
        for vav_id in building2.vavs:
            self.assertIn("Building2", vav_id)

        # Central plant should be in correct building
        self.assertGreater(len(building1.chillers), 0)
        self.assertEqual(len(building1.boilers), 0)
        self.assertEqual(len(building2.chillers), 0)
        self.assertGreater(len(building2.boilers), 0)


class TestEquipmentBelongsToBuilding(unittest.TestCase):
    """Tests for the _equipment_belongs_to_building helper method."""

    def setUp(self):
        """Set up test parser."""
        # We need a TTL file to initialize the parser
        self.ttl_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "data",
            "brick_schemas",
            "bldg1.ttl",
        )
        if os.path.exists(self.ttl_path):
            self.parser = BrickParser(self.ttl_path)
        else:
            self.parser = None

    def test_explicit_mapping(self):
        """Test that explicit isPartOf mapping takes precedence."""
        if self.parser is None:
            self.skipTest("TTL file not found")

        mapping = {"AHU1": "Building1", "AHU2": "Building2"}

        # Explicit mapping should work
        self.assertTrue(self.parser._equipment_belongs_to_building("AHU1", "Building1", mapping))
        self.assertFalse(self.parser._equipment_belongs_to_building("AHU1", "Building2", mapping))

    def test_naming_convention_prefix(self):
        """Test building detection via naming prefix."""
        if self.parser is None:
            self.skipTest("TTL file not found")

        # Equipment ID starts with building ID
        self.assertTrue(
            self.parser._equipment_belongs_to_building("Building1_AHU01", "Building1", {})
        )
        self.assertFalse(
            self.parser._equipment_belongs_to_building("Building1_AHU01", "Building2", {})
        )

    def test_naming_convention_contains(self):
        """Test building detection when building ID is contained in equipment ID."""
        if self.parser is None:
            self.skipTest("TTL file not found")

        # Equipment ID contains building ID
        self.assertTrue(self.parser._equipment_belongs_to_building("AHU_bldg1_01", "bldg1", {}))
        self.assertFalse(self.parser._equipment_belongs_to_building("AHU_bldg2_01", "bldg1", {}))

    def test_no_match(self):
        """Test when equipment doesn't match any building."""
        if self.parser is None:
            self.skipTest("TTL file not found")

        self.assertFalse(self.parser._equipment_belongs_to_building("RandomAHU", "Building1", {}))


if __name__ == "__main__":
    unittest.main()

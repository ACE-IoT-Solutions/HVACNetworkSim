"""Tests for Brick campus parsing helpers."""

from pathlib import Path
import unittest

from src.brick.parser import BrickParser


class TestBrickParserBACnetAnnotations(unittest.TestCase):
    """Verify optional BACnet metadata can be driven from Brick TTL examples."""

    def test_collision_example_extracts_explicit_device_ids(self):
        ttl_path = (
            Path(__file__).resolve().parent.parent
            / "examples"
            / "multi_building_campus_collisions.ttl"
        )
        parser = BrickParser(str(ttl_path))
        campus = parser.extract_all_buildings()

        self.assertEqual(campus.buildings["Building1"].ahus["Building1_AHU01"]["device_id"], 100)
        self.assertEqual(campus.buildings["Building2"].vavs["Building2_VAV201"]["device_id"], 100)


if __name__ == "__main__":
    unittest.main()

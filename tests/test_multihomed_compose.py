"""Tests for the direct multi-network compose template."""

from pathlib import Path
import unittest


class TestMultihomedCompose(unittest.TestCase):
    """Verify the multihomed harness stays isolated and collision-focused."""

    def test_multihomed_compose_has_two_isolated_networks_and_collision_ids(self):
        compose_path = Path(__file__).resolve().parent.parent / "docker-compose.multihomed.yml"
        compose = compose_path.read_text()

        self.assertIn("10.11.0.0/24", compose)
        self.assertIn("10.12.0.0/24", compose)
        self.assertIn('BACNET_IP: "10.11.0.10"', compose)
        self.assertIn('BACNET_IP: "10.12.0.10"', compose)
        self.assertEqual(compose.count('BACNET_DEVICE_ID: "100"'), 2)
        self.assertIn('BACNET_NETWORK_NUMBER: "100"', compose)
        self.assertIn('BACNET_NETWORK_NUMBER: "200"', compose)
        self.assertNotIn("campus-router", compose)
        self.assertNotIn("ace-acl-bbmd", compose)
        self.assertNotIn("ports:", compose)


if __name__ == "__main__":
    unittest.main()

"""Tests for secure campus compose generation defaults."""

import unittest

from campus.generate_campus import (
    generate_bbmd_config,
    generate_compose,
    resolve_campus_ttl,
)
from src.brick.campus import BuildingStructure, CampusStructure


class TestCampusGenerationSecurity(unittest.TestCase):
    """Verify campus generation keeps external exposure opt-in."""

    def build_campus(self, building_name: str = "HQ: East") -> CampusStructure:
        campus = CampusStructure()
        campus.add_building(BuildingStructure(name=building_name))
        return campus

    def build_two_building_campus(self) -> CampusStructure:
        campus = CampusStructure()
        campus.add_building(BuildingStructure(name="Building1"))
        campus.add_building(BuildingStructure(name="Building2"))
        return campus

    def test_bbmd_config_disables_foreign_devices_by_default(self):
        bbmd_config = generate_bbmd_config(1, 2, expose_bacnet=False)
        self.assertIn("accept_foreign_devices: false", bbmd_config)

    def test_bbmd_config_enables_foreign_devices_when_exposed(self):
        bbmd_config = generate_bbmd_config(1, 2, expose_bacnet=True)
        self.assertIn("accept_foreign_devices: true", bbmd_config)

    def test_compose_keeps_bacnet_exposure_opt_in_but_enables_fault_control(self):
        compose = generate_compose(
            self.build_campus(),
            "examples/multi_building_campus.ttl",
            expose_bacnet=False,
        )
        self.assertNotIn(':47808/udp"', compose)
        self.assertIn("127.0.0.1:19101:9100/tcp", compose)
        self.assertIn("127.0.0.1:19201:9100/tcp", compose)
        self.assertIn('FAULT_CONTROL_PORT: "9100"', compose)
        self.assertIn('BUILDING_NAME: "HQ: East"', compose)
        self.assertIn("container_name: campus-sim-hq_east", compose)

    def test_compose_publishes_bacnet_ports_when_explicitly_enabled(self):
        compose = generate_compose(
            self.build_campus("Building One"),
            "examples/multi_building_campus.ttl",
            expose_bacnet=True,
        )
        self.assertIn('"47809:47808/udp"', compose)
        self.assertIn("127.0.0.1:19101:9100/tcp", compose)

    def test_multi_network_scenario_assigns_explicit_network_numbers(self):
        compose = generate_compose(
            self.build_two_building_campus(),
            "examples/multi_building_campus.ttl",
            scenario="multi-network",
        )
        self.assertIn("# Scenario: multi-network", compose)
        self.assertIn('BACNET_NETWORK_NUMBER: "100"', compose)
        self.assertIn('BACNET_NETWORK_NUMBER: "200"', compose)

    def test_default_scenario_omits_explicit_network_numbers(self):
        compose = generate_compose(
            self.build_two_building_campus(),
            "examples/multi_building_campus.ttl",
        )
        self.assertNotIn("BACNET_NETWORK_NUMBER", compose)

    def test_bdt_asymmetry_scenario_overrides_one_bbmd_peer_table(self):
        compose = generate_compose(
            self.build_two_building_campus(),
            "examples/multi_building_campus.ttl",
            scenario="multi-network-bdt-asymmetry",
        )
        self.assertIn("# Scenario: multi-network-bdt-asymmetry", compose)
        self.assertIn('BBMD_BDT_PEERS: "10.2.0.100:47808"', compose)

        bbmd_config = generate_bbmd_config(
            2,
            2,
            peer_entries=("10.2.0.100:47808",),
        )
        self.assertIn('  - "10.2.0.100/24:47808"', bbmd_config)
        self.assertNotIn("10.1.0.100/32:47808", bbmd_config)

    def test_duplicate_router_claim_scenario_sets_extra_router_claims(self):
        compose = generate_compose(
            self.build_two_building_campus(),
            "examples/multi_building_campus.ttl",
            scenario="multi-network-duplicate-router-claim",
        )
        self.assertIn(
            'ROUTER_CLAIMED_NETWORKS: "2100"',
            compose,
        )

    def test_campus_router_keeps_legacy_254_alias(self):
        compose = generate_compose(
            self.build_two_building_campus(),
            "examples/multi_building_campus.ttl",
            scenario="multi-network",
        )
        self.assertIn("ipv4_address: 10.1.0.102", compose)
        self.assertIn('ip addr add 10.1.0.254/24 dev "$$iface"', compose)
        self.assertIn("compat 10.1.0.254", compose)

    def test_collision_scenario_uses_checked_in_example_by_default(self):
        ttl_path = resolve_campus_ttl(None, "multi-network-collisions")
        self.assertEqual(ttl_path.name, "multi_building_campus_collisions.ttl")

    def test_bdt_asymmetry_scenario_uses_standard_example(self):
        ttl_path = resolve_campus_ttl(None, "multi-network-bdt-asymmetry")
        self.assertEqual(ttl_path.name, "multi_building_campus.ttl")


if __name__ == "__main__":
    unittest.main()

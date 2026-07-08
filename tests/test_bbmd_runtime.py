"""Tests for campus BBMD runtime helpers."""

import unittest

from campus.bbmd_runtime import (
    build_bdt_entries,
    parse_rendered_bbmd_config,
    render_bbmd_config,
)


class TestBBMDRuntime(unittest.TestCase):
    """Validate BBMD config rendering and peer normalization."""

    def test_default_bdt_entries_are_symmetric(self):
        self.assertEqual(
            build_bdt_entries(1, 2),
            ["10.1.0.100/24:47808", "10.2.0.100/32:47808"],
        )

    def test_explicit_bdt_entries_normalize_self_and_peer_masks(self):
        self.assertEqual(
            build_bdt_entries(
                1,
                2,
                peer_overrides=("10.1.0.100:47808", "10.2.0.100:47808"),
            ),
            ["10.1.0.100/24:47808", "10.2.0.100/32:47808"],
        )

    def test_rendered_config_round_trips(self):
        config_text = render_bbmd_config(
            bbmd_address="10.1.0.100/24:47808",
            device_id=998,
            device_name="BBMD-Building1",
            bdt_entries=["10.1.0.100/24:47808", "10.2.0.100/32:47808"],
            accept_foreign_devices=False,
        )

        self.assertEqual(
            parse_rendered_bbmd_config(config_text),
            {
                "bbmd_address": "10.1.0.100/24:47808",
                "device_id": 998,
                "device_name": "BBMD-Building1",
                "bdt_entries": ["10.1.0.100/24:47808", "10.2.0.100/32:47808"],
                "accept_foreign_devices": False,
            },
        )


if __name__ == "__main__":
    unittest.main()

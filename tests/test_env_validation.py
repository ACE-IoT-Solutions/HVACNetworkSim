"""Tests for environment validation helpers."""

import unittest

from src.core.env_validation import (
    EnvironmentValidationError,
    format_container_command,
    normalize_bacnet_address,
    parse_boolean_value,
    parse_extra_env_var,
    validate_bacnet_network_number,
)


class TestEnvValidation(unittest.TestCase):
    """Validate CLI and runtime environment parsing."""

    def test_normalize_bacnet_address_from_full_value(self):
        self.assertEqual(
            normalize_bacnet_address(address="192.168.10.42/24"),
            "192.168.10.42/24",
        )

    def test_normalize_bacnet_address_from_ip_and_subnet(self):
        self.assertEqual(
            normalize_bacnet_address(ip="10.10.10.5", subnet="16"),
            "10.10.10.5/16",
        )

    def test_normalize_bacnet_address_rejects_invalid_input(self):
        with self.assertRaises(EnvironmentValidationError):
            normalize_bacnet_address(address="bad-value")

    def test_parse_boolean_value_rejects_unknown_value(self):
        with self.assertRaises(EnvironmentValidationError):
            parse_boolean_value("sometimes", variable_name="INJECT_ERRORS")

    def test_parse_extra_env_var_rejects_managed_runtime_keys(self):
        with self.assertRaises(EnvironmentValidationError):
            parse_extra_env_var("SIMULATION_MODE", "custom")

    def test_parse_extra_env_var_validates_and_normalizes_port(self):
        key, value = parse_extra_env_var("bacnet_port", "47809")
        self.assertEqual(key, "BACNET_PORT")
        self.assertEqual(value, "47809")

    def test_parse_extra_env_var_validates_network_number(self):
        key, value = parse_extra_env_var("bacnet_network_number", "200")
        self.assertEqual(key, "BACNET_NETWORK_NUMBER")
        self.assertEqual(value, "200")

    def test_validate_bacnet_network_number_rejects_out_of_range_value(self):
        with self.assertRaises(EnvironmentValidationError):
            validate_bacnet_network_number("65535")

    def test_format_container_command_redacts_env_values(self):
        command = [
            "podman",
            "run",
            "-e",
            "BACNET_PORT=47809",
            "-e",
            "TOKEN=super-secret",
            "hvac-simulator",
        ]
        formatted = format_container_command(command)
        self.assertIn("BACNET_PORT=<redacted>", formatted)
        self.assertIn("TOKEN=<redacted>", formatted)
        self.assertNotIn("super-secret", formatted)


if __name__ == "__main__":
    unittest.main()

"""Tests for BBMD and error injection functionality."""

import unittest

from src.bacnet.bbmd import BBMDConfig, BDTEntry
from src.bacnet.errors import (
    BACnetValidator,
    DetectedError,
    ErrorInjectionConfig,
)


class TestBDTEntry(unittest.TestCase):
    """Tests for BDTEntry dataclass."""

    def test_initialization_defaults(self):
        """Test BDTEntry initializes with correct defaults."""
        entry = BDTEntry(ip_address="192.168.1.100")

        self.assertEqual(entry.ip_address, "192.168.1.100")
        self.assertEqual(entry.port, 47808)
        self.assertEqual(entry.mask, "255.255.255.255")

    def test_initialization_custom(self):
        """Test BDTEntry with custom values."""
        entry = BDTEntry(
            ip_address="10.0.0.1",
            port=47809,
            mask="255.255.0.0",
        )

        self.assertEqual(entry.ip_address, "10.0.0.1")
        self.assertEqual(entry.port, 47809)
        self.assertEqual(entry.mask, "255.255.0.0")


class TestBBMDConfig(unittest.TestCase):
    """Tests for BBMDConfig dataclass."""

    def test_initialization_defaults(self):
        """Test BBMDConfig initializes with correct defaults."""
        config = BBMDConfig(ip_address="192.168.1.1/24")

        self.assertEqual(config.ip_address, "192.168.1.1/24")
        self.assertEqual(config.port, 47808)
        self.assertIsNone(config.device_id)
        self.assertIsNone(config.device_name)
        self.assertEqual(config.bdt_entries, [])
        self.assertIsNone(config.building_name)
        self.assertEqual(config.foreign_device_ttl, 300)

    def test_initialization_custom(self):
        """Test BBMDConfig with custom values."""
        config = BBMDConfig(
            ip_address="10.0.0.1/16",
            port=47809,
            device_id=900,
            device_name="TestBBMD",
            building_name="Building1",
            foreign_device_ttl=600,
        )

        self.assertEqual(config.ip_address, "10.0.0.1/16")
        self.assertEqual(config.port, 47809)
        self.assertEqual(config.device_id, 900)
        self.assertEqual(config.device_name, "TestBBMD")
        self.assertEqual(config.building_name, "Building1")
        self.assertEqual(config.foreign_device_ttl, 600)

    def test_add_peer(self):
        """Test adding peer BBMDs."""
        config = BBMDConfig(ip_address="192.168.1.1/24")

        config.add_peer("192.168.2.1")
        config.add_peer("192.168.3.1", port=47809)

        self.assertEqual(len(config.bdt_entries), 2)
        self.assertEqual(config.bdt_entries[0].ip_address, "192.168.2.1")
        self.assertEqual(config.bdt_entries[0].port, 47808)
        self.assertEqual(config.bdt_entries[1].ip_address, "192.168.3.1")
        self.assertEqual(config.bdt_entries[1].port, 47809)


class TestErrorInjectionConfig(unittest.TestCase):
    """Tests for ErrorInjectionConfig dataclass."""

    def test_initialization_defaults(self):
        """Test ErrorInjectionConfig initializes with correct defaults."""
        config = ErrorInjectionConfig()

        self.assertEqual(config.duplicate_device_ids, [])
        self.assertEqual(config.duplicate_network_numbers, [])
        self.assertEqual(config.duplicate_routers, [])
        self.assertIsNone(config.random_seed)

    def test_has_errors_false(self):
        """Test has_errors returns False when no errors configured."""
        config = ErrorInjectionConfig()
        self.assertFalse(config.has_errors())

    def test_has_errors_true_device_ids(self):
        """Test has_errors returns True when device IDs configured."""
        config = ErrorInjectionConfig(duplicate_device_ids=[(1001, 1)])
        self.assertTrue(config.has_errors())

    def test_has_errors_true_network_numbers(self):
        """Test has_errors returns True when network numbers configured."""
        config = ErrorInjectionConfig(duplicate_network_numbers=[(100, 2)])
        self.assertTrue(config.has_errors())

    def test_has_errors_true_routers(self):
        """Test has_errors returns True when routers configured."""
        config = ErrorInjectionConfig(duplicate_routers=[100, 200])
        self.assertTrue(config.has_errors())


class TestDetectedError(unittest.TestCase):
    """Tests for DetectedError dataclass."""

    def test_initialization(self):
        """Test DetectedError initializes correctly."""
        error = DetectedError(
            error_type="duplicate_device_id",
            identifier=1001,
            locations=["network1:Device1", "network2:Device2"],
            severity="error",
            description="Device ID 1001 is used by 2 devices",
        )

        self.assertEqual(error.error_type, "duplicate_device_id")
        self.assertEqual(error.identifier, 1001)
        self.assertEqual(len(error.locations), 2)
        self.assertEqual(error.severity, "error")
        self.assertIn("1001", error.description)


class TestBACnetValidator(unittest.TestCase):
    """Tests for BACnetValidator class."""

    def test_initialization(self):
        """Test BACnetValidator initializes correctly."""
        validator = BACnetValidator()
        self.assertEqual(validator.errors, [])

    def test_has_errors_false(self):
        """Test has_errors returns False when no errors."""
        validator = BACnetValidator()
        self.assertFalse(validator.has_errors())

    def test_has_errors_true(self):
        """Test has_errors returns True when errors exist."""
        validator = BACnetValidator()
        validator.errors.append(
            DetectedError(
                error_type="test",
                identifier=1,
                locations=["loc1"],
            )
        )
        self.assertTrue(validator.has_errors())

    def test_get_error_count(self):
        """Test get_error_count returns correct count."""
        validator = BACnetValidator()
        self.assertEqual(validator.get_error_count(), 0)

        validator.errors.append(DetectedError(error_type="test1", identifier=1, locations=["loc1"]))
        validator.errors.append(DetectedError(error_type="test2", identifier=2, locations=["loc2"]))
        self.assertEqual(validator.get_error_count(), 2)

    def test_get_errors_by_type(self):
        """Test get_errors_by_type filters correctly."""
        validator = BACnetValidator()
        validator.errors.append(
            DetectedError(error_type="type_a", identifier=1, locations=["loc1"])
        )
        validator.errors.append(
            DetectedError(error_type="type_b", identifier=2, locations=["loc2"])
        )
        validator.errors.append(
            DetectedError(error_type="type_a", identifier=3, locations=["loc3"])
        )

        type_a_errors = validator.get_errors_by_type("type_a")
        self.assertEqual(len(type_a_errors), 2)

        type_b_errors = validator.get_errors_by_type("type_b")
        self.assertEqual(len(type_b_errors), 1)

        type_c_errors = validator.get_errors_by_type("type_c")
        self.assertEqual(len(type_c_errors), 0)

    def test_generate_report_no_errors(self):
        """Test report generation with no errors."""
        validator = BACnetValidator()
        report = validator.generate_report()
        self.assertIn("No BACnet configuration errors detected", report)

    def test_generate_report_with_errors(self):
        """Test report generation with errors."""
        validator = BACnetValidator()
        validator.errors.append(
            DetectedError(
                error_type="duplicate_device_id",
                identifier=1001,
                locations=["net1:dev1", "net2:dev2"],
                description="Device ID 1001 is used by 2 devices",
            )
        )

        report = validator.generate_report()
        self.assertIn("BACnet Configuration Error Report", report)
        self.assertIn("DUPLICATE DEVICE ID", report)
        self.assertIn("1001", report)
        self.assertIn("net1:dev1", report)


if __name__ == "__main__":
    unittest.main()

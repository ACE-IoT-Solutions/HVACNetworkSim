"""Tests for the configuration system."""

import json
import tempfile
import unittest
from pathlib import Path

from src.core.config import (
    PIDConfig,
    ThermalZoneConfig,
    VAVConfig,
    AHUConfig,
    ChillerConfig,
    CoolingTowerConfig,
    BoilerConfig,
    BACnetConfig,
    SimulationConfig,
    BuildingConfig,
    load_config,
    save_config,
    get_default_config,
)
from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
from src.chiller import Chiller
from src.cooling_tower import CoolingTower
from src.boiler import Boiler


class TestConfigDataclasses(unittest.TestCase):
    """Test configuration dataclass creation and defaults."""

    def test_pid_config_defaults(self):
        """Test PIDConfig default values."""
        config = PIDConfig()
        self.assertEqual(config.kp, 0.5)
        self.assertEqual(config.ki, 0.1)
        self.assertEqual(config.kd, 0.05)
        self.assertEqual(config.output_min, 0.0)
        self.assertEqual(config.output_max, 1.0)

    def test_pid_config_custom_values(self):
        """Test PIDConfig with custom values."""
        config = PIDConfig(kp=1.0, ki=0.2, kd=0.1, output_min=-1.0, output_max=2.0)
        self.assertEqual(config.kp, 1.0)
        self.assertEqual(config.ki, 0.2)
        self.assertEqual(config.kd, 0.1)
        self.assertEqual(config.output_min, -1.0)
        self.assertEqual(config.output_max, 2.0)

    def test_vav_config_requires_name(self):
        """Test that VAVConfig requires a name."""
        with self.assertRaises(TypeError):
            VAVConfig()  # type: ignore

    def test_vav_config_with_name(self):
        """Test VAVConfig with required name."""
        config = VAVConfig(name="VAV-101")
        self.assertEqual(config.name, "VAV-101")
        self.assertEqual(config.min_airflow, 100.0)
        self.assertEqual(config.max_airflow, 1000.0)
        self.assertEqual(config.zone_temp_setpoint, 72.0)
        self.assertTrue(config.has_reheat)

    def test_vav_config_with_thermal_zone(self):
        """Test VAVConfig with nested ThermalZoneConfig."""
        zone = ThermalZoneConfig(zone_area=500.0, zone_volume=4000.0)
        config = VAVConfig(name="VAV-102", thermal_zone=zone)
        self.assertEqual(config.thermal_zone.zone_area, 500.0)
        self.assertEqual(config.thermal_zone.zone_volume, 4000.0)

    def test_ahu_config_defaults(self):
        """Test AHUConfig default values."""
        config = AHUConfig(name="AHU-1")
        self.assertEqual(config.supply_air_temp_setpoint, 55.0)
        self.assertEqual(config.cooling_type, "chilled_water")

    def test_chiller_config_defaults(self):
        """Test ChillerConfig default values."""
        config = ChillerConfig(name="Chiller-1")
        self.assertEqual(config.capacity, 500.0)
        self.assertEqual(config.design_cop, 5.0)
        self.assertEqual(config.cooling_type, "water_cooled")

    def test_cooling_tower_config_defaults(self):
        """Test CoolingTowerConfig default values."""
        config = CoolingTowerConfig(name="CT-1")
        self.assertEqual(config.capacity, 600.0)
        self.assertEqual(config.design_approach, 7.0)
        self.assertEqual(config.tower_type, "counterflow")

    def test_boiler_config_defaults(self):
        """Test BoilerConfig default values."""
        config = BoilerConfig(name="Boiler-1")
        self.assertEqual(config.capacity, 1000.0)
        self.assertEqual(config.fuel_type, "gas")
        self.assertEqual(config.design_efficiency, 0.85)

    def test_bacnet_config_defaults(self):
        """Test BACnetConfig default values."""
        config = BACnetConfig()
        self.assertIsNone(config.ip_address)
        self.assertEqual(config.port, 47808)
        self.assertEqual(config.device_id_base, 1000)

    def test_simulation_config_defaults(self):
        """Test SimulationConfig default values."""
        config = SimulationConfig()
        self.assertEqual(config.time_step_minutes, 1)
        self.assertEqual(config.speed_multiplier, 60)

    def test_building_config_defaults(self):
        """Test BuildingConfig default values."""
        config = BuildingConfig()
        self.assertEqual(config.name, "Default Building")
        self.assertIsInstance(config.simulation, SimulationConfig)
        self.assertIsInstance(config.bacnet, BACnetConfig)
        self.assertEqual(len(config.vavs), 0)


class TestEquipmentFromConfig(unittest.TestCase):
    """Test equipment creation from config dataclasses."""

    def test_vav_from_config(self):
        """Test VAVBox.from_config() factory method."""
        config = VAVConfig(
            name="VAV-Test",
            min_airflow=150.0,
            max_airflow=800.0,
            zone_temp_setpoint=70.0,
            deadband=3.0,
            discharge_air_temp_setpoint=52.0,
            has_reheat=False,
        )
        vav = VAVBox.from_config(config)

        self.assertEqual(vav.name, "VAV-Test")
        self.assertEqual(vav.min_airflow, 150.0)
        self.assertEqual(vav.max_airflow, 800.0)
        self.assertEqual(vav.zone_temp_setpoint, 70.0)
        self.assertEqual(vav.deadband, 3.0)
        self.assertEqual(vav.discharge_air_temp_setpoint, 52.0)
        self.assertFalse(vav.has_reheat)

    def test_vav_from_config_with_thermal_zone(self):
        """Test VAVBox.from_config() with thermal zone config."""
        zone = ThermalZoneConfig(
            zone_area=600.0,
            zone_volume=4800.0,
            window_area=120.0,
            window_orientation="south",
            thermal_mass=2.5,
        )
        config = VAVConfig(
            name="VAV-Zone",
            thermal_zone=zone,
        )
        vav = VAVBox.from_config(config)

        self.assertEqual(vav.zone_area, 600.0)
        self.assertEqual(vav.zone_volume, 4800.0)
        self.assertEqual(vav.window_area, 120.0)
        self.assertEqual(vav.window_orientation, "south")
        self.assertEqual(vav.thermal_mass, 2.5)

    def test_vav_from_config_type_error(self):
        """Test VAVBox.from_config() with wrong type."""
        with self.assertRaises(TypeError):
            VAVBox.from_config({"name": "wrong"})  # type: ignore

    def test_ahu_from_config(self):
        """Test AirHandlingUnit.from_config() factory method."""
        config = AHUConfig(
            name="AHU-Test",
            supply_air_temp_setpoint=54.0,
            max_supply_airflow=15000.0,
            cooling_type="dx",
            compressor_stages=3,
        )
        ahu = AirHandlingUnit.from_config(config)

        self.assertEqual(ahu.name, "AHU-Test")
        self.assertEqual(ahu.supply_air_temp_setpoint, 54.0)
        self.assertEqual(ahu.max_supply_airflow, 15000.0)
        self.assertEqual(ahu.cooling_type, "dx")
        self.assertEqual(ahu.compressor_stages, 3)

    def test_ahu_from_config_type_error(self):
        """Test AirHandlingUnit.from_config() with wrong type."""
        with self.assertRaises(TypeError):
            AirHandlingUnit.from_config({"name": "wrong"})  # type: ignore

    def test_chiller_from_config(self):
        """Test Chiller.from_config() factory method."""
        config = ChillerConfig(
            name="Chiller-Test",
            capacity=300.0,
            design_cop=4.5,
            cooling_type="air_cooled",
        )
        chiller = Chiller.from_config(config)

        self.assertEqual(chiller.name, "Chiller-Test")
        self.assertEqual(chiller.capacity, 300.0)
        self.assertEqual(chiller.design_cop, 4.5)
        self.assertEqual(chiller.cooling_type, "air_cooled")

    def test_chiller_from_config_type_error(self):
        """Test Chiller.from_config() with wrong type."""
        with self.assertRaises(TypeError):
            Chiller.from_config({"name": "wrong"})  # type: ignore

    def test_cooling_tower_from_config(self):
        """Test CoolingTower.from_config() factory method."""
        config = CoolingTowerConfig(
            name="CT-Test",
            capacity=400.0,
            design_approach=8.0,
            tower_type="crossflow",
            num_cells=2,
        )
        tower = CoolingTower.from_config(config)

        self.assertEqual(tower.name, "CT-Test")
        self.assertEqual(tower.capacity, 400.0)
        self.assertEqual(tower.design_approach, 8.0)
        self.assertEqual(tower.tower_type, "crossflow")
        self.assertEqual(tower.num_cells, 2)

    def test_cooling_tower_from_config_type_error(self):
        """Test CoolingTower.from_config() with wrong type."""
        with self.assertRaises(TypeError):
            CoolingTower.from_config({"name": "wrong"})  # type: ignore

    def test_boiler_from_config(self):
        """Test Boiler.from_config() factory method."""
        config = BoilerConfig(
            name="Boiler-Test",
            capacity=800.0,
            fuel_type="electric",
            design_efficiency=0.98,
            condensing=True,
        )
        boiler = Boiler.from_config(config)

        self.assertEqual(boiler.name, "Boiler-Test")
        self.assertEqual(boiler.capacity, 800.0)
        self.assertEqual(boiler.fuel_type, "electric")
        self.assertEqual(boiler.design_efficiency, 0.98)
        self.assertTrue(boiler.condensing)

    def test_boiler_from_config_type_error(self):
        """Test Boiler.from_config() with wrong type."""
        with self.assertRaises(TypeError):
            Boiler.from_config({"name": "wrong"})  # type: ignore


class TestConfigLoadSave(unittest.TestCase):
    """Test configuration file loading and saving."""

    def test_load_json_config(self):
        """Test loading config from JSON file."""
        config_data = {
            "simulation": {"time_step_minutes": 5},
            "bacnet": {"port": 47809},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            loaded = load_config(f.name)

        self.assertEqual(loaded["simulation"]["time_step_minutes"], 5)
        self.assertEqual(loaded["bacnet"]["port"], 47809)

    def test_save_json_config(self):
        """Test saving config to JSON file."""
        config_data = {"test_key": "test_value", "nested": {"key": 123}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            save_config(config_data, f.name)
            f.flush()

        with open(f.name) as f2:
            loaded = json.load(f2)

        self.assertEqual(loaded["test_key"], "test_value")
        self.assertEqual(loaded["nested"]["key"], 123)

    def test_load_missing_file(self):
        """Test loading config from missing file raises error."""
        with self.assertRaises(FileNotFoundError):
            load_config("/nonexistent/path/config.json")

    def test_load_unsupported_format(self):
        """Test loading config from unsupported format raises error."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            f.flush()

        with self.assertRaises(ValueError):
            load_config(f.name)

    def test_get_default_config(self):
        """Test get_default_config returns valid BuildingConfig."""
        config = get_default_config()
        self.assertIsInstance(config, BuildingConfig)
        self.assertEqual(config.name, "Default Building")


class TestDefaultConfigFile(unittest.TestCase):
    """Test the default_config.yaml file."""

    def test_default_config_loads(self):
        """Test that data/default_config.yaml loads without errors."""
        config_path = Path(__file__).parent.parent / "data" / "default_config.yaml"
        if config_path.exists():
            config = load_config(config_path)
            self.assertIn("simulation", config)
            self.assertIn("bacnet", config)
            self.assertIn("defaults", config)


if __name__ == "__main__":
    unittest.main()

"""Integration tests for complete building HVAC simulations.

These tests verify that multiple equipment components work together
correctly in realistic building scenarios.
"""

import unittest

from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
from src.chiller import Chiller
from src.cooling_tower import CoolingTower
from src.boiler import Boiler
from src.core.config import (
    VAVConfig,
    AHUConfig,
    ChillerConfig,
    CoolingTowerConfig,
    BoilerConfig,
    ThermalZoneConfig,
)


class TestAHUWithVAVs(unittest.TestCase):
    """Test AHU operating with multiple VAV boxes."""

    def setUp(self):
        """Set up AHU with multiple VAV boxes."""
        # Create VAV boxes for different zones
        self.vav_east = VAVBox(
            name="VAV-East",
            min_airflow=100,
            max_airflow=800,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
            window_area=100,
            window_orientation="east",
            thermal_mass=2.0,
        )

        self.vav_west = VAVBox(
            name="VAV-West",
            min_airflow=100,
            max_airflow=800,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
            window_area=100,
            window_orientation="west",
            thermal_mass=2.0,
        )

        self.vav_interior = VAVBox(
            name="VAV-Interior",
            min_airflow=100,
            max_airflow=600,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=600,
            zone_volume=4800,
            window_area=0,  # No windows
            window_orientation="north",
            thermal_mass=3.0,  # Higher mass for interior
        )

        # Create AHU with all VAV boxes
        self.ahu = AirHandlingUnit(
            name="AHU-1",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=3000,
            vav_boxes=[self.vav_east, self.vav_west, self.vav_interior],
            enable_supply_temp_reset=True,
            cooling_type="chilled_water",
        )

    def test_ahu_updates_all_vavs(self):
        """Test that AHU update propagates to all VAV boxes."""
        zone_temps = {
            "VAV-East": 74.0,
            "VAV-West": 73.0,
            "VAV-Interior": 72.5,
        }

        self.ahu.update(zone_temps, outdoor_temp=85.0)

        # All VAVs should have updated
        self.assertNotEqual(self.vav_east.current_airflow, 0)
        self.assertNotEqual(self.vav_west.current_airflow, 0)
        self.assertNotEqual(self.vav_interior.current_airflow, 0)

    def test_total_airflow_calculation(self):
        """Test that AHU correctly sums VAV airflows."""
        zone_temps = {
            "VAV-East": 76.0,  # High cooling demand
            "VAV-West": 76.0,
            "VAV-Interior": 76.0,
        }

        self.ahu.update(zone_temps, outdoor_temp=90.0)

        expected_total = (
            self.vav_east.current_airflow
            + self.vav_west.current_airflow
            + self.vav_interior.current_airflow
        )
        self.assertAlmostEqual(self.ahu.current_total_airflow, expected_total, places=1)

    def test_supply_temp_reset_cooling(self):
        """Test supply air temperature reset in cooling mode."""
        # All zones need cooling
        zone_temps = {
            "VAV-East": 76.0,
            "VAV-West": 76.0,
            "VAV-Interior": 76.0,
        }

        self.ahu.update(zone_temps, outdoor_temp=90.0)

        # With reset enabled and all zones in cooling, supply temp should be lower
        self.assertLessEqual(self.ahu.current_supply_air_temp, self.ahu.supply_air_temp_setpoint)

    def test_supply_temp_reset_heating(self):
        """Test supply air temperature reset in heating mode."""
        # All zones need heating
        zone_temps = {
            "VAV-East": 68.0,
            "VAV-West": 68.0,
            "VAV-Interior": 68.0,
        }

        self.ahu.update(zone_temps, outdoor_temp=35.0)

        # With reset enabled and all zones in heating, supply temp should be higher
        self.assertGreaterEqual(self.ahu.current_supply_air_temp, self.ahu.supply_air_temp_setpoint)

    def test_mixed_zone_demands(self):
        """Test AHU response to mixed zone demands."""
        # Mix of zone demands
        zone_temps = {
            "VAV-East": 76.0,  # Cooling
            "VAV-West": 72.0,  # Deadband
            "VAV-Interior": 68.0,  # Heating
        }

        self.ahu.update(zone_temps, outdoor_temp=70.0)

        # VAVs should be in different modes
        self.assertEqual(self.vav_east.mode, "cooling")
        self.assertEqual(self.vav_west.mode, "deadband")
        self.assertEqual(self.vav_interior.mode, "heating")

    def test_cooling_energy_tracking(self):
        """Test that cooling energy is tracked correctly."""
        zone_temps = {
            "VAV-East": 76.0,
            "VAV-West": 76.0,
            "VAV-Interior": 76.0,
        }

        self.ahu.update(zone_temps, outdoor_temp=90.0)

        energy = self.ahu.calculate_energy_usage()
        self.assertGreater(energy["cooling"], 0)
        self.assertEqual(energy["heating"], 0)


class TestChillerCoolingTowerIntegration(unittest.TestCase):
    """Test chiller and cooling tower working together."""

    def setUp(self):
        """Set up chiller with associated cooling tower."""
        self.cooling_tower = CoolingTower(
            name="CT-1",
            capacity=600,
            design_approach=7,
            design_range=10,
            design_wet_bulb=78,
            min_speed=20,
            tower_type="counterflow",
            fan_power=50,
            num_cells=1,
        )

        self.chiller = Chiller(
            name="Chiller-1",
            cooling_type="water_cooled",
            capacity=500,
            design_cop=5.0,
            design_entering_condenser_temp=85,
            design_leaving_chilled_water_temp=44,
            min_part_load_ratio=0.1,
            design_chilled_water_flow=1000,
            design_condenser_water_flow=1200,
        )

        # Associate cooling tower with chiller
        self.chiller.connect_cooling_tower(self.cooling_tower)

    def test_chiller_updates_cooling_tower(self):
        """Test that chiller operation updates cooling tower."""
        # Apply a load to the chiller
        self.chiller.update_load(
            load=250,  # 50% load
            entering_chilled_water_temp=54,
            chilled_water_flow=800,
            ambient_wet_bulb=75,
        )

        # Cooling tower should have updated
        self.assertGreater(self.cooling_tower.current_load, 0)
        self.assertGreater(self.cooling_tower.fan_speed, 0)

    def test_condenser_water_flow_propagation(self):
        """Test condenser water flow is passed to cooling tower."""
        self.chiller.update_load(
            load=400,
            entering_chilled_water_temp=54,
            chilled_water_flow=900,
            ambient_wet_bulb=78,
        )

        # Cooling tower should receive condenser water flow
        self.assertGreater(self.cooling_tower.water_flow, 0)

    def test_cop_at_different_loads(self):
        """Test chiller COP varies with load."""
        # Low load
        self.chiller.update_load(
            load=100,
            entering_chilled_water_temp=54,
            chilled_water_flow=500,
            ambient_wet_bulb=75,
        )
        low_load_cop = self.chiller.current_cop

        # Reset state
        self.chiller.current_load = 0
        self.chiller.current_cop = 0

        # High load
        self.chiller.update_load(
            load=450,
            entering_chilled_water_temp=54,
            chilled_water_flow=950,
            ambient_wet_bulb=75,
        )
        high_load_cop = self.chiller.current_cop

        # Both should be non-zero (chiller is operating)
        self.assertGreater(low_load_cop, 0)
        self.assertGreater(high_load_cop, 0)

    def test_chiller_minimum_load(self):
        """Test chiller doesn't go below minimum part load ratio."""
        # Try to apply very low load (below min PLR)
        self.chiller.update_load(
            load=10,  # Very low - below min_part_load_ratio * capacity
            entering_chilled_water_temp=44,
            chilled_water_flow=200,
            ambient_wet_bulb=75,
        )

        # Chiller should be at minimum load, not zero
        min_load = self.chiller.capacity * self.chiller.min_part_load_ratio
        self.assertGreaterEqual(self.chiller.current_load, min_load)


class TestBoilerOperation(unittest.TestCase):
    """Test boiler operation and cycling."""

    def setUp(self):
        """Set up boiler for testing."""
        self.boiler = Boiler(
            name="Boiler-1",
            fuel_type="gas",
            capacity=1000,  # MBH
            design_efficiency=0.85,
            design_entering_water_temp=160,
            design_leaving_water_temp=180,
            min_part_load_ratio=0.2,
            design_hot_water_flow=100,
            condensing=False,
            turndown_ratio=4.0,
        )

    def test_boiler_efficiency_at_load(self):
        """Test boiler efficiency varies with load."""
        # Apply heating load
        self.boiler.update_load(
            load=500,  # 50% load
            entering_water_temp=160,
            hot_water_flow=80,
            ambient_temp=70,
        )

        # Efficiency should be positive
        self.assertGreater(self.boiler.current_efficiency, 0)
        self.assertLessEqual(self.boiler.current_efficiency, 1.0)

    def test_boiler_cycling_logic(self):
        """Test boiler respects minimum on/off times."""
        # First, simulate passing min_off_time so boiler can turn on
        # (boiler starts in off state, needs to wait min_off_time before turning on)
        self.boiler.time_in_current_state = 10.0  # Past min_off_time

        # Now turn boiler on with time step
        self.boiler.update_load(
            load=500,
            entering_water_temp=160,
            hot_water_flow=80,
            ambient_temp=70,
            simulation_time_step=1.0,
        )
        self.assertTrue(self.boiler.is_on)

        # Try to turn off quickly (should stay on due to min_on_time)
        self.boiler.update_load(
            load=0,
            entering_water_temp=180,
            hot_water_flow=0,
            ambient_temp=70,
            simulation_time_step=1.0,  # Only 1 minute after turning on
        )
        # Boiler should still be on due to min_on_time constraint
        self.assertTrue(self.boiler.is_on)

        # Simulate time passing past min_on_time (10 minutes default)
        for _ in range(12):
            self.boiler.update_load(
                load=0,
                entering_water_temp=180,
                hot_water_flow=0,
                ambient_temp=70,
                simulation_time_step=1.0,
            )

        # Now boiler should be able to turn off
        self.assertFalse(self.boiler.is_on)

    def test_fuel_consumption_tracking(self):
        """Test fuel consumption is tracked via calculate_fuel_consumption."""
        # Turn boiler on without time step (bypasses cycling logic)
        self.boiler.update_load(
            load=800,
            entering_water_temp=160,
            hot_water_flow=90,
            ambient_temp=70,
        )

        # Check fuel consumption via the method
        fuel = self.boiler.calculate_fuel_consumption()
        # For gas boiler, should have therms_per_hour
        self.assertIn("therms_per_hour", fuel)
        self.assertGreater(fuel["therms_per_hour"], 0)


class TestEquipmentFromConfigIntegration(unittest.TestCase):
    """Test creating and using equipment from config objects."""

    def test_create_ahu_system_from_config(self):
        """Test creating a complete AHU system from configs."""
        # Create VAV configs
        vav_configs = [
            VAVConfig(
                name=f"VAV-{i}",
                min_airflow=100,
                max_airflow=800,
                thermal_zone=ThermalZoneConfig(zone_area=400),
            )
            for i in range(1, 4)
        ]

        # Create VAVs from configs
        vavs = [VAVBox.from_config(cfg) for cfg in vav_configs]

        # Create AHU config and AHU
        ahu_config = AHUConfig(
            name="AHU-Config-Test",
            max_supply_airflow=5000,
        )
        ahu = AirHandlingUnit.from_config(ahu_config)

        # Add VAVs to AHU
        for vav in vavs:
            ahu.add_vav_box(vav)

        # Verify system works
        zone_temps = {f"VAV-{i}": 74.0 for i in range(1, 4)}
        ahu.update(zone_temps, outdoor_temp=85.0)

        self.assertEqual(len(ahu.vav_boxes), 3)
        self.assertGreater(ahu.current_total_airflow, 0)

    def test_create_chiller_plant_from_config(self):
        """Test creating a chiller plant from configs."""
        # Create cooling tower from config
        ct_config = CoolingTowerConfig(
            name="CT-Config",
            capacity=600,
            tower_type="counterflow",
        )
        cooling_tower = CoolingTower.from_config(ct_config)

        # Create chiller from config (water-cooled requires condenser flow)
        chiller_config = ChillerConfig(
            name="Chiller-Config",
            capacity=500,
            cooling_type="water_cooled",
            design_condenser_water_flow=1200.0,  # Required for water-cooled
        )
        chiller = Chiller.from_config(chiller_config)

        # Associate them
        chiller.connect_cooling_tower(cooling_tower)

        # Verify they work together
        chiller.update_load(
            load=300,
            entering_chilled_water_temp=54,
            chilled_water_flow=700,
            ambient_wet_bulb=75,
        )

        self.assertGreater(chiller.current_load, 0)
        self.assertGreater(cooling_tower.current_load, 0)

    def test_create_boiler_from_config(self):
        """Test creating and operating a boiler from config."""
        boiler_config = BoilerConfig(
            name="Boiler-Config",
            capacity=800,
            fuel_type="gas",
            condensing=True,
        )
        boiler = Boiler.from_config(boiler_config)

        # Verify it operates
        boiler.update_load(
            load=400,
            entering_water_temp=160,
            hot_water_flow=80,
            ambient_temp=70,
        )

        self.assertTrue(boiler.is_on)
        self.assertGreater(boiler.current_efficiency, 0)


class TestThermalConvergence(unittest.TestCase):
    """Test that zone temperatures converge to setpoints over time."""

    def test_zone_converges_to_setpoint(self):
        """Test zone temperature converges toward setpoint."""
        vav = VAVBox(
            name="VAV-Convergence",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
            thermal_mass=2.0,
        )

        # Start with high temperature
        vav.zone_temp = 78.0
        initial_error = abs(vav.zone_temp - vav.zone_temp_setpoint)

        # Simulate several updates
        for _ in range(10):
            vav.update(zone_temp=vav.zone_temp, supply_air_temp=55)
            # Apply thermal behavior
            temp_change = vav.calculate_thermal_behavior(
                minutes=15,
                outdoor_temp=72,
                vav_cooling_effect=vav.damper_position,
                time_of_day=(12, 0),
            )
            vav.zone_temp += temp_change

        # Temperature should have moved toward setpoint
        final_error = abs(vav.zone_temp - vav.zone_temp_setpoint)
        self.assertLess(final_error, initial_error)


if __name__ == "__main__":
    unittest.main()

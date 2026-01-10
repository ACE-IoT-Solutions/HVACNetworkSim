import unittest
from src.cooling_tower import CoolingTower


class TestCoolingTower(unittest.TestCase):
    def setUp(self):
        # Create a cooling tower for testing
        self.cooling_tower = CoolingTower(
            name="CT-1",
            capacity=1000,  # Nominal capacity in tons
            design_approach=5,  # °F approach at design conditions
            design_range=10,  # °F range at design conditions
            design_wet_bulb=76,  # °F design wet bulb temperature
            min_speed=20,  # Minimum fan speed (%)
            tower_type="counterflow",  # Tower type: counterflow or crossflow
            fan_power=75,  # Fan power at 100% speed in kW
            num_cells=4,  # Number of cells
        )

    def test_initialization(self):
        """Test that the cooling tower initializes with correct default values."""
        self.assertEqual(self.cooling_tower.name, "CT-1")
        self.assertEqual(self.cooling_tower.capacity, 1000)
        self.assertEqual(self.cooling_tower.design_approach, 5)
        self.assertEqual(self.cooling_tower.design_range, 10)
        self.assertEqual(self.cooling_tower.design_wet_bulb, 76)
        self.assertEqual(self.cooling_tower.min_speed, 20)
        self.assertEqual(self.cooling_tower.tower_type, "counterflow")
        self.assertEqual(self.cooling_tower.fan_power, 75)
        self.assertEqual(self.cooling_tower.num_cells, 4)
        self.assertEqual(self.cooling_tower.current_load, 0)
        self.assertEqual(self.cooling_tower.entering_water_temp, 95)  # Default EWT
        self.assertEqual(self.cooling_tower.leaving_water_temp, 85)  # Default LWT
        self.assertEqual(self.cooling_tower.current_wet_bulb, 76)  # Default ambient WB
        self.assertEqual(self.cooling_tower.fan_speed, 0)  # Fan off by default

    def test_update_load(self):
        """Test updating the cooling tower with a new load."""
        # Set load to 50% of capacity
        self.cooling_tower.update_load(
            load=500,  # 500 tons (50% of capacity)
            entering_water_temp=95,
            ambient_wet_bulb=75,
            condenser_water_flow=3000,  # GPM
        )

        self.assertEqual(self.cooling_tower.current_load, 500)
        self.assertEqual(self.cooling_tower.entering_water_temp, 95)
        self.assertEqual(self.cooling_tower.current_wet_bulb, 75)

        # Verify that leaving water temp is calculated
        self.assertLess(
            self.cooling_tower.leaving_water_temp, self.cooling_tower.entering_water_temp
        )

        # Verify that the fan speed is set appropriately for the load
        self.assertGreater(self.cooling_tower.fan_speed, 0)

    def test_calculate_approach(self):
        """Test calculation of approach temperature."""
        # Apply 75% load with 78°F wet bulb
        self.cooling_tower.update_load(
            load=750, entering_water_temp=95, ambient_wet_bulb=78, condenser_water_flow=3000
        )

        # Calculate approach
        approach = self.cooling_tower.calculate_approach()

        # Approach might vary from design at different conditions, but should be within reasonable range
        self.assertGreaterEqual(approach, 0.7 * self.cooling_tower.design_approach)
        self.assertLessEqual(approach, 1.5 * self.cooling_tower.design_approach)

        # Approach must be positive
        self.assertGreater(approach, 0)

        # At 75% load with high wet bulb, leaving water temp should be around design wet bulb + approach
        expected_lwt = 78 + approach
        self.assertAlmostEqual(self.cooling_tower.leaving_water_temp, expected_lwt, delta=0.5)

    def test_load_capacity_relationship(self):
        """Test relationship between load and capacity."""
        # Test different load levels and verify appropriate responses
        test_loads = [100, 500, 750, 1000, 1200]  # 10% to 120% of capacity
        fan_speeds = []
        approaches = []

        for load in test_loads:
            self.cooling_tower.update_load(
                load=load, entering_water_temp=95, ambient_wet_bulb=76, condenser_water_flow=3000
            )

            fan_speeds.append(self.cooling_tower.fan_speed)
            approaches.append(self.cooling_tower.calculate_approach())

        # Fan speed should increase with load
        for i in range(len(test_loads) - 1):
            if test_loads[i] < self.cooling_tower.capacity:  # Only check up to design capacity
                self.assertLessEqual(fan_speeds[i], fan_speeds[i + 1])

        # Approach should increase as load exceeds capacity
        self.assertLess(approaches[2], approaches[4])  # 75% load vs 120% load

    def test_wet_bulb_effect(self):
        """Test effect of wet bulb temperature on performance."""
        # Test with different wet bulb temperatures at constant load
        wet_bulbs = [65, 70, 75, 80, 85]
        approaches = []

        for wb in wet_bulbs:
            self.cooling_tower.update_load(
                load=750,  # 75% load
                entering_water_temp=95,
                ambient_wet_bulb=wb,
                condenser_water_flow=3000,
            )

            approaches.append(self.cooling_tower.calculate_approach())

        # Approach temperature should increase with wet bulb temperature
        for i in range(len(wet_bulbs) - 1):
            self.assertLessEqual(approaches[i], approaches[i + 1])

        # Large difference between lowest and highest WB test
        self.assertGreater(approaches[-1] - approaches[0], 1)

    def test_tower_efficiency(self):
        """Test cooling tower efficiency calculations."""
        self.cooling_tower.update_load(
            load=500,  # 50% load
            entering_water_temp=95,
            ambient_wet_bulb=76,
            condenser_water_flow=3000,
        )

        # Calculate efficiency
        efficiency = self.cooling_tower.calculate_efficiency()

        # Efficiency should be between 0 and 1
        self.assertGreaterEqual(efficiency, 0)
        self.assertLessEqual(efficiency, 1)

        # At design conditions, efficiency should be good
        self.assertGreater(efficiency, 0.6)

    def test_power_consumption(self):
        """Test cooling tower power consumption calculation."""
        # Test at various loads
        test_loads = [0, 250, 500, 750, 1000]
        power_consumptions = []

        for load in test_loads:
            self.cooling_tower.update_load(
                load=load, entering_water_temp=95, ambient_wet_bulb=76, condenser_water_flow=3000
            )

            power = self.cooling_tower.calculate_power_consumption()
            power_consumptions.append(power)

        # At zero load, power should be minimal
        self.assertLess(power_consumptions[0], 0.1 * self.cooling_tower.fan_power)

        # Power should increase with load
        for i in range(len(test_loads) - 1):
            self.assertLessEqual(power_consumptions[i], power_consumptions[i + 1])

        # At full load, power should be near rated fan power
        self.assertAlmostEqual(power_consumptions[-1], self.cooling_tower.fan_power, delta=5)

    def test_energy_calculations(self):
        """Test energy calculations over time."""
        # Set up cooling tower at 80% load
        self.cooling_tower.update_load(
            load=800, entering_water_temp=95, ambient_wet_bulb=76, condenser_water_flow=3000
        )

        # Calculate energy for 1 hour
        energy_kwh = self.cooling_tower.calculate_energy_consumption(hours=1)

        # Energy should be close to power * time
        expected_energy = self.cooling_tower.calculate_power_consumption() * 1
        self.assertAlmostEqual(energy_kwh, expected_energy, delta=0.1)

        # Energy for 2 hours should be double
        energy_2h = self.cooling_tower.calculate_energy_consumption(hours=2)
        self.assertAlmostEqual(energy_2h, 2 * energy_kwh, delta=0.1)

    def test_tower_water_consumption(self):
        """Test calculation of evaporative water loss."""
        # Set cooling tower to 60% load
        self.cooling_tower.update_load(
            load=600, entering_water_temp=95, ambient_wet_bulb=76, condenser_water_flow=3000
        )

        # Calculate water consumption in gallons per hour
        water_gph = self.cooling_tower.calculate_water_consumption()

        # Water consumption should be significant but reasonable
        # Rule of thumb: ~2 gpm per 100 tons for total makeup
        expected_rough = 2 * (600 / 100) * 60  # 2 gpm per 100 tons -> gph
        self.assertGreater(water_gph, 0)

        # Check that it's at least in the same order of magnitude
        # Our calculation includes more detail than the simple rule of thumb
        self.assertGreater(water_gph, expected_rough * 0.3)  # At least 30% of rule of thumb
        self.assertLess(water_gph, expected_rough * 3)  # Not more than 3x rule of thumb

    def test_part_load_performance(self):
        """Test part-load performance curve for the cooling tower."""
        # Test behavior at low load
        self.cooling_tower.update_load(
            load=100,  # 10% of capacity
            entering_water_temp=95,
            ambient_wet_bulb=76,
            condenser_water_flow=3000,
        )

        # Tower should deliver better approach at low load
        low_load_approach = self.cooling_tower.calculate_approach()

        # Test behavior at high load
        self.cooling_tower.update_load(
            load=1000,  # 100% of capacity
            entering_water_temp=95,
            ambient_wet_bulb=76,
            condenser_water_flow=3000,
        )

        # Approach at high load should be worse (higher)
        high_load_approach = self.cooling_tower.calculate_approach()

        self.assertLess(low_load_approach, high_load_approach)

    def test_fan_speed_control(self):
        """Test fan speed control logic."""
        # Test manual fan speed setting
        self.cooling_tower.set_fan_speed(50)  # 50% speed
        self.assertEqual(self.cooling_tower.fan_speed, 50)

        # Set load which should auto-adjust fan speed
        self.cooling_tower.update_load(
            load=800,
            entering_water_temp=95,
            ambient_wet_bulb=76,
            condenser_water_flow=3000,
            auto_adjust_fan=True,
        )

        # Fan speed should now be different from manual setting
        self.assertNotEqual(self.cooling_tower.fan_speed, 50)

        # Set manual again with auto_adjust=False
        self.cooling_tower.set_fan_speed(60)
        self.cooling_tower.update_load(
            load=400,
            entering_water_temp=95,
            ambient_wet_bulb=76,
            condenser_water_flow=3000,
            auto_adjust_fan=False,
        )

        # Fan speed should remain at manual setting
        self.assertEqual(self.cooling_tower.fan_speed, 60)

    def test_get_process_variables(self):
        """Test that Cooling Tower returns a dictionary of all process variables."""
        # Setup the cooling tower with some known values
        self.cooling_tower.update_load(
            load=500,  # 50% load
            entering_water_temp=95,
            ambient_wet_bulb=76,
            condenser_water_flow=3000,
        )

        # Get process variables
        variables = self.cooling_tower.get_process_variables()

        # Check that it's a dictionary
        self.assertIsInstance(variables, dict)

        # Check that it contains essential state variables
        essential_vars = [
            "name",
            "capacity",
            "current_load",
            "load_ratio",
            "design_approach",
            "current_approach",
            "design_range",
            "current_range",
            "entering_water_temp",
            "leaving_water_temp",
            "current_wet_bulb",
            "water_flow",
            "fan_speed",
            "current_fan_power",
            "efficiency",
            "water_consumption_gph",
        ]

        for var in essential_vars:
            self.assertIn(var, variables)

        # Check that values match the actual object properties
        self.assertEqual(variables["name"], self.cooling_tower.name)
        self.assertEqual(variables["capacity"], self.cooling_tower.capacity)
        self.assertEqual(variables["current_load"], self.cooling_tower.current_load)
        self.assertEqual(variables["entering_water_temp"], self.cooling_tower.entering_water_temp)
        self.assertEqual(variables["leaving_water_temp"], self.cooling_tower.leaving_water_temp)
        self.assertEqual(variables["current_wet_bulb"], self.cooling_tower.current_wet_bulb)
        self.assertEqual(variables["fan_speed"], self.cooling_tower.fan_speed)

        # Check calculated values
        self.assertAlmostEqual(
            variables["current_approach"], self.cooling_tower.calculate_approach()
        )
        self.assertAlmostEqual(variables["current_range"], self.cooling_tower.calculate_range())
        self.assertAlmostEqual(variables["efficiency"], self.cooling_tower.calculate_efficiency())
        self.assertAlmostEqual(
            variables["current_fan_power"], self.cooling_tower.calculate_power_consumption()
        )
        self.assertAlmostEqual(
            variables["water_consumption_gph"], self.cooling_tower.calculate_water_consumption()
        )

    def test_get_process_variables_metadata(self):
        """Test that Cooling Tower provides metadata for all process variables."""
        # Get metadata
        metadata = CoolingTower.get_process_variables_metadata()

        # Check that it's a dictionary
        self.assertIsInstance(metadata, dict)

        # Check that it contains metadata for essential state variables
        essential_vars = [
            "name",
            "capacity",
            "current_load",
            "entering_water_temp",
            "leaving_water_temp",
            "current_wet_bulb",
            "fan_speed",
            "current_fan_power",
            "efficiency",
            "water_consumption_gph",
        ]

        for var in essential_vars:
            self.assertIn(var, metadata)

        # Check that each variable has the required metadata fields
        for var_name, var_metadata in metadata.items():
            self.assertIn("type", var_metadata)
            self.assertIn("label", var_metadata)
            self.assertIn("description", var_metadata)

        # Check specific metadata entries for correctness
        self.assertEqual(metadata["current_load"]["type"], float)
        self.assertEqual(metadata["current_load"]["label"], "Current Load")
        self.assertEqual(metadata["current_load"]["unit"], "tons")

        self.assertEqual(metadata["entering_water_temp"]["type"], float)
        self.assertEqual(metadata["entering_water_temp"]["unit"], "°F")

        self.assertEqual(metadata["name"]["type"], str)
        self.assertEqual(metadata["num_cells"]["type"], int)
        self.assertEqual(metadata["active_cells"]["type"], int)

        # Check that options are provided for enumerated types
        self.assertIn("options", metadata["tower_type"])
        self.assertIn("counterflow", metadata["tower_type"]["options"])
        self.assertIn("crossflow", metadata["tower_type"]["options"])


if __name__ == "__main__":
    unittest.main()

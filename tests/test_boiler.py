import unittest
from src.boiler import Boiler


class TestBoiler(unittest.TestCase):
    def setUp(self):
        # Create both types of boilers for testing
        self.gas_boiler = Boiler(
            name="Boiler-1",
            fuel_type="gas",
            capacity=2000,  # MBH (thousand BTU/hr)
            design_efficiency=0.85,  # 85% efficiency at design conditions
            design_entering_water_temp=160,  # °F
            design_leaving_water_temp=180,  # °F
            min_part_load_ratio=0.2,  # 20% minimum load
            design_hot_water_flow=240,  # GPM
            condensing=True,  # Condensing boiler type
            turndown_ratio=5.0,  # 5:1 turndown ratio
        )

        self.electric_boiler = Boiler(
            name="Boiler-2",
            fuel_type="electric",
            capacity=1500,  # MBH (thousand BTU/hr)
            design_efficiency=0.98,  # 98% efficiency (electric)
            design_entering_water_temp=160,  # °F
            design_leaving_water_temp=180,  # °F
            min_part_load_ratio=0.1,  # 10% minimum load
            design_hot_water_flow=180,  # GPM
            condensing=False,  # Not applicable for electric
            turndown_ratio=10.0,  # Higher turndown for electric
        )

    def test_initialization(self):
        """Test that boilers initialize with correct default values."""
        # Gas boiler
        self.assertEqual(self.gas_boiler.name, "Boiler-1")
        self.assertEqual(self.gas_boiler.fuel_type, "gas")
        self.assertEqual(self.gas_boiler.capacity, 2000)
        self.assertEqual(self.gas_boiler.design_efficiency, 0.85)
        self.assertEqual(self.gas_boiler.design_entering_water_temp, 160)
        self.assertEqual(self.gas_boiler.design_leaving_water_temp, 180)
        self.assertEqual(self.gas_boiler.min_part_load_ratio, 0.2)
        self.assertEqual(self.gas_boiler.design_hot_water_flow, 240)
        self.assertTrue(self.gas_boiler.condensing)
        self.assertEqual(self.gas_boiler.turndown_ratio, 5.0)
        self.assertEqual(self.gas_boiler.current_load, 0)
        self.assertEqual(self.gas_boiler.entering_water_temp, 160)  # Default EWT
        self.assertEqual(self.gas_boiler.leaving_water_temp, 180)  # Default LWT
        self.assertEqual(self.gas_boiler.current_efficiency, 0)  # Off by default

        # Electric boiler
        self.assertEqual(self.electric_boiler.name, "Boiler-2")
        self.assertEqual(self.electric_boiler.fuel_type, "electric")
        self.assertEqual(self.electric_boiler.capacity, 1500)
        self.assertEqual(self.electric_boiler.design_efficiency, 0.98)
        self.assertEqual(self.electric_boiler.design_entering_water_temp, 160)
        self.assertEqual(self.electric_boiler.design_leaving_water_temp, 180)
        self.assertEqual(self.electric_boiler.min_part_load_ratio, 0.1)
        self.assertEqual(self.electric_boiler.design_hot_water_flow, 180)
        self.assertFalse(self.electric_boiler.condensing)
        self.assertEqual(self.electric_boiler.turndown_ratio, 10.0)

    def test_gas_boiler_update_load(self):
        """Test updating the gas boiler with a new load."""
        # Set load to 50% of capacity
        self.gas_boiler.update_load(
            load=1000,  # 1000 MBH (50% of capacity)
            entering_water_temp=160,
            hot_water_flow=240,
            ambient_temp=70,
        )

        self.assertEqual(self.gas_boiler.current_load, 1000)
        self.assertEqual(self.gas_boiler.entering_water_temp, 160)

        # Verify that leaving water temp is maintained near design
        self.assertAlmostEqual(self.gas_boiler.leaving_water_temp, 180, delta=0.5)

        # Verify efficiency is calculated and reasonable
        self.assertGreater(self.gas_boiler.current_efficiency, 0)
        self.assertLess(self.gas_boiler.current_efficiency, 1)  # Efficiency < 100%

    def test_electric_boiler_update_load(self):
        """Test updating the electric boiler with a new load."""
        # Set load to a 50% of capacity
        self.electric_boiler.update_load(
            load=750,  # 750 MBH (50% of capacity)
            entering_water_temp=160,
            hot_water_flow=180,
            ambient_temp=70,
        )

        self.assertEqual(self.electric_boiler.current_load, 750)
        self.assertEqual(self.electric_boiler.entering_water_temp, 160)

        # Verify that leaving water temp is maintained near design
        self.assertAlmostEqual(self.electric_boiler.leaving_water_temp, 180, delta=0.5)

        # Electric boiler efficiency should be constant regardless of load
        self.assertAlmostEqual(
            self.electric_boiler.current_efficiency,
            self.electric_boiler.design_efficiency,
            delta=0.01,
        )

    def test_capacity_limits(self):
        """Test boiler behavior at capacity limits."""
        # Test gas boiler at overload (120% capacity)
        self.gas_boiler.update_load(
            load=2400,  # 120% of capacity
            entering_water_temp=160,
            hot_water_flow=240,
            ambient_temp=70,
        )

        # Boiler should limit to maximum capacity
        self.assertEqual(self.gas_boiler.current_load, 2000)

        # Leaving water temp might not reach setpoint under overload
        self.assertLessEqual(self.gas_boiler.leaving_water_temp, 180)

        # Test electric boiler below minimum part load
        self.electric_boiler.update_load(
            load=100,  # 6.7% of capacity - below minimum
            entering_water_temp=160,
            hot_water_flow=180,
            ambient_temp=70,
        )

        # Boiler should operate at minimum part load
        self.assertEqual(
            self.electric_boiler.current_load,
            self.electric_boiler.capacity * self.electric_boiler.min_part_load_ratio,
        )

    def test_efficiency_vs_return_temp(self):
        """Test relationship between return water temperature and efficiency for condensing gas boiler."""
        # Test with significantly different return water temperatures for gas condensing boiler
        return_temps = [
            90,
            120,
            140,
            160,
        ]  # Using lower temp to ensure condensing benefit is significant
        efficiencies = []

        # Modified test to focus on just the extreme cases
        for ewt in return_temps:
            self.gas_boiler.update_load(
                load=1000,  # 50% load
                entering_water_temp=ewt,
                hot_water_flow=240,
                ambient_temp=70,
            )
            efficiencies.append(self.gas_boiler.current_efficiency)

        # Lowest return temp should have highest efficiency
        self.assertGreater(efficiencies[0], efficiencies[-1])

        # Significant improvement at low return temps where condensing occurs
        self.assertGreater(efficiencies[0] - efficiencies[-1], 0.05)

    def test_efficiency_vs_load_relationship(self):
        """Test relationship between load and efficiency."""
        # Test different load levels for gas boiler
        gas_loads = [400, 1000, 1500, 2000]  # 20% to 100% of capacity
        gas_efficiencies = []

        for load in gas_loads:
            self.gas_boiler.update_load(
                load=load, entering_water_temp=160, hot_water_flow=240, ambient_temp=70
            )
            gas_efficiencies.append(self.gas_boiler.current_efficiency)

        # Efficiency should be best at optimum load, worse at extremes
        # For most boilers, efficiency peaks around 50-80% load
        self.assertLess(gas_efficiencies[0], gas_efficiencies[1])  # 20% vs 50%
        self.assertLess(gas_efficiencies[3], gas_efficiencies[2])  # 100% vs 75%

        # Test different load levels for electric boiler
        electric_loads = [150, 500, 1000, 1500]  # 10% to 100% of capacity
        electric_efficiencies = []

        for load in electric_loads:
            self.electric_boiler.update_load(
                load=load, entering_water_temp=160, hot_water_flow=180, ambient_temp=70
            )
            electric_efficiencies.append(self.electric_boiler.current_efficiency)

        # Electric efficiency should be relatively constant across loads
        for i in range(1, len(electric_efficiencies)):
            self.assertAlmostEqual(electric_efficiencies[0], electric_efficiencies[i], delta=0.02)

    def test_fuel_consumption(self):
        """Test fuel consumption calculation."""
        # Update gas boiler at 50% load
        self.gas_boiler.update_load(
            load=1000, entering_water_temp=160, hot_water_flow=240, ambient_temp=70
        )

        # Calculate gas consumption
        gas_consumption = self.gas_boiler.calculate_fuel_consumption()

        # Gas consumption should be in therms or cubic feet
        self.assertGreater(gas_consumption["therms_per_hour"], 0)
        self.assertGreater(gas_consumption["cubic_feet_per_hour"], 0)

        # Consumption should relate to load and efficiency
        expected_therms = self.gas_boiler.current_load / (self.gas_boiler.current_efficiency * 100)
        self.assertAlmostEqual(gas_consumption["therms_per_hour"], expected_therms, delta=1)

        # Update electric boiler at 50% load
        self.electric_boiler.update_load(
            load=750, entering_water_temp=160, hot_water_flow=180, ambient_temp=70
        )

        # Calculate electricity consumption
        electric_consumption = self.electric_boiler.calculate_fuel_consumption()

        # Electricity consumption should be in kWh
        self.assertGreater(electric_consumption["kilowatt_hours"], 0)

        # Consumption should relate to load and efficiency
        expected_kwh = (
            self.electric_boiler.current_load * 0.293
        ) / self.electric_boiler.current_efficiency
        self.assertAlmostEqual(electric_consumption["kilowatt_hours"], expected_kwh, delta=1)

    def test_ambient_temp_effect(self):
        """Test effect of ambient temperature on gas boiler efficiency."""
        # Test with different ambient temperatures for gas boiler
        ambient_temps = [30, 50, 70, 90]
        efficiencies = []

        for temp in ambient_temps:
            self.gas_boiler.update_load(
                load=1000,  # 50% load
                entering_water_temp=160,
                hot_water_flow=240,
                ambient_temp=temp,
            )
            efficiencies.append(self.gas_boiler.current_efficiency)

        # Efficiency should decrease slightly with lower ambient temps due to jacket losses
        # The effect is minor but should be present
        self.assertLessEqual(efficiencies[0], efficiencies[-1])

    def test_energy_calculations(self):
        """Test energy calculations over time."""
        # Update gas boiler at 60% load
        self.gas_boiler.update_load(
            load=1200, entering_water_temp=160, hot_water_flow=240, ambient_temp=70
        )

        # Calculate energy for 1 hour
        energy_consumption = self.gas_boiler.calculate_energy_consumption(hours=1)

        # Energy should be in various units
        self.assertIn("mmbtu", energy_consumption)
        self.assertIn("therms", energy_consumption)

        # Energy should be close to load * time / efficiency
        expected_mmbtu = 1.2 * 1 / self.gas_boiler.current_efficiency  # 1200 MBH = 1.2 MMBTU/hr
        self.assertAlmostEqual(energy_consumption["mmbtu"], expected_mmbtu, delta=0.1)

        # Energy for 2 hours should be double
        energy_2h = self.gas_boiler.calculate_energy_consumption(hours=2)
        self.assertAlmostEqual(energy_2h["mmbtu"], 2 * energy_consumption["mmbtu"], delta=0.1)

        # Update electric boiler
        self.electric_boiler.update_load(
            load=750, entering_water_temp=160, hot_water_flow=180, ambient_temp=70
        )

        # Calculate electric energy for 1 hour
        electric_consumption = self.electric_boiler.calculate_energy_consumption(hours=1)

        # Energy should be in kilowatt-hours
        self.assertIn("kwh", electric_consumption)

        # Check electric energy calculation
        expected_kwh = (
            (750 * 0.293) / self.electric_boiler.current_efficiency * 1
        )  # 750 MBH * conversion to kW * 1 hour
        self.assertAlmostEqual(electric_consumption["kwh"], expected_kwh, delta=1)

    def test_leaving_water_temp_control(self):
        """Test control of leaving hot water temperature."""
        # Test gas boiler with different setpoint
        self.gas_boiler.set_leaving_water_temp_setpoint(190)
        self.gas_boiler.update_load(
            load=1000,
            entering_water_temp=170,  # High return temp
            hot_water_flow=240,
            ambient_temp=70,
        )

        # Verify LWT is near new setpoint
        self.assertAlmostEqual(self.gas_boiler.leaving_water_temp, 190, delta=1)

        # Store efficiency at high temp operation
        high_temp_efficiency = self.gas_boiler.current_efficiency

        # Test with much lower setpoint and return temp (better for condensing boilers)
        self.gas_boiler.set_leaving_water_temp_setpoint(140)
        self.gas_boiler.update_load(
            load=1000,
            entering_water_temp=100,  # Very low return temp to ensure condensing
            hot_water_flow=240,
            ambient_temp=70,
        )

        # LWT should be near new setpoint
        self.assertAlmostEqual(self.gas_boiler.leaving_water_temp, 140, delta=1)

        # For condensing boilers, efficiency should be better at lower temperatures with low return temps
        low_temp_efficiency = self.gas_boiler.current_efficiency

        # Verify significant efficiency gain at condensing conditions
        self.assertGreater(low_temp_efficiency, high_temp_efficiency)

    def test_boiler_cycling(self):
        """Test boiler cycling behaviors."""
        # Set up cycling test for gas boiler
        self.gas_boiler.set_cycling_parameters(
            min_on_time=10,  # minutes
            min_off_time=5,  # minutes
            cycles_per_hour_limit=6,
        )

        # Start boiler with small load
        self.gas_boiler.update_load(
            load=500,  # 25% of capacity
            entering_water_temp=160,
            hot_water_flow=240,
            ambient_temp=70,
        )

        # Boiler should be on
        self.assertTrue(self.gas_boiler.is_on)

        # Try to turn off immediately (should not work due to min_on_time)
        self.gas_boiler.update_load(
            load=0,
            entering_water_temp=160,
            hot_water_flow=240,
            ambient_temp=70,
            simulation_time_step=5,  # 5 minutes - less than min_on_time
        )

        # Boiler should still be on
        self.assertTrue(self.gas_boiler.is_on)

        # Turn off after min_on_time
        self.gas_boiler.update_load(
            load=0,
            entering_water_temp=160,
            hot_water_flow=240,
            ambient_temp=70,
            simulation_time_step=10,  # 10 minutes - equal to min_on_time
        )

        # Boiler should now be off
        self.assertFalse(self.gas_boiler.is_on)

        # Count cycles
        initial_cycles = self.gas_boiler.cycles_in_current_hour

        # Generate several cycles
        for i in range(4):
            # Turn on
            self.gas_boiler.update_load(
                load=500,
                entering_water_temp=160,
                hot_water_flow=240,
                ambient_temp=70,
                simulation_time_step=5,
            )

            # Turn off
            self.gas_boiler.update_load(
                load=0,
                entering_water_temp=160,
                hot_water_flow=240,
                ambient_temp=70,
                simulation_time_step=10,
            )

        # Should have counted new cycles
        self.assertGreater(self.gas_boiler.cycles_in_current_hour, initial_cycles)

        # Should not exceed cycles_per_hour_limit
        self.assertLessEqual(
            self.gas_boiler.cycles_in_current_hour, self.gas_boiler.cycles_per_hour_limit
        )

    def test_get_process_variables(self):
        """Test that Boiler returns a dictionary of all process variables."""
        # Set up both boilers with some known values
        self.gas_boiler.update_load(
            load=1000,  # 50% load
            entering_water_temp=160,
            hot_water_flow=240,
            ambient_temp=70,
        )

        self.electric_boiler.update_load(
            load=750,  # 50% load
            entering_water_temp=160,
            hot_water_flow=180,
            ambient_temp=70,
        )

        # Get process variables for both boiler types
        gas_vars = self.gas_boiler.get_process_variables()
        electric_vars = self.electric_boiler.get_process_variables()

        # Check that they're dictionaries
        self.assertIsInstance(gas_vars, dict)
        self.assertIsInstance(electric_vars, dict)

        # Check that both contain essential state variables
        essential_vars = [
            "name",
            "fuel_type",
            "capacity",
            "current_load",
            "load_ratio",
            "current_efficiency",
            "entering_water_temp",
            "leaving_water_temp",
            "hot_water_flow",
            "design_hot_water_flow",
            "is_on",
            "ambient_temp",
        ]

        for var in essential_vars:
            self.assertIn(var, gas_vars)
            self.assertIn(var, electric_vars)

        # Check that values match the actual object properties
        self.assertEqual(gas_vars["name"], self.gas_boiler.name)
        self.assertEqual(gas_vars["fuel_type"], self.gas_boiler.fuel_type)
        self.assertEqual(gas_vars["capacity"], self.gas_boiler.capacity)
        self.assertEqual(gas_vars["current_load"], self.gas_boiler.current_load)
        self.assertEqual(gas_vars["entering_water_temp"], self.gas_boiler.entering_water_temp)
        self.assertEqual(gas_vars["leaving_water_temp"], self.gas_boiler.leaving_water_temp)
        self.assertEqual(gas_vars["is_on"], self.gas_boiler.is_on)

        # Check cycling variables
        cycling_vars = ["min_on_time", "min_off_time", "cycles_per_hour_limit"]
        for var in cycling_vars:
            self.assertIn(var, gas_vars)
            self.assertIn(var, electric_vars)

        # Check fuel-specific variables
        self.assertIn("therms_per_hour", gas_vars)
        self.assertIn("cubic_feet_per_hour", gas_vars)
        self.assertIn("kilowatt_hours", electric_vars)

        # Gas boiler should not have electric variables
        self.assertNotIn("kilowatt_hours", gas_vars)

        # Electric boiler should not have gas variables
        self.assertNotIn("therms_per_hour", electric_vars)
        self.assertNotIn("cubic_feet_per_hour", electric_vars)

    def test_get_process_variables_metadata(self):
        """Test that Boiler provides metadata for all process variables."""
        # Get metadata
        metadata = Boiler.get_process_variables_metadata()

        # Check that it's a dictionary
        self.assertIsInstance(metadata, dict)

        # Check that it contains metadata for essential state variables
        essential_vars = [
            "name",
            "fuel_type",
            "capacity",
            "current_load",
            "load_ratio",
            "current_efficiency",
            "entering_water_temp",
            "leaving_water_temp",
            "is_on",
            "ambient_temp",
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
        self.assertEqual(metadata["current_load"]["unit"], "MBH")

        self.assertEqual(metadata["current_efficiency"]["type"], float)
        self.assertEqual(metadata["current_efficiency"]["unit"], "fraction")

        self.assertEqual(metadata["name"]["type"], str)
        self.assertEqual(metadata["fuel_type"]["type"], str)
        self.assertEqual(metadata["is_on"]["type"], bool)
        self.assertEqual(metadata["condensing"]["type"], bool)

        # Check cycling-related variables
        cycling_vars = ["min_on_time", "min_off_time", "cycles_per_hour_limit"]
        for var in cycling_vars:
            self.assertIn(var, metadata)

        # Check that options are provided for enumerated types
        self.assertIn("options", metadata["fuel_type"])
        self.assertIn("gas", metadata["fuel_type"]["options"])
        self.assertIn("electric", metadata["fuel_type"]["options"])

        # Check that fuel-specific variables are included
        self.assertIn("therms_per_hour", metadata)
        self.assertIn("cubic_feet_per_hour", metadata)
        self.assertIn("kilowatt_hours", metadata)


if __name__ == "__main__":
    unittest.main()

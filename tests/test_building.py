import unittest
import pytest
import math
from datetime import datetime, timedelta
from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
from src.building import Building

class TestBuilding(unittest.TestCase):
    def setUp(self):
        # Create a sample building for testing
        self.building = Building(
            name="Test Building",
            location="New York, NY",
            latitude=40.7128,
            longitude=-74.0060,
            floor_area=50000,  # sq ft
            num_floors=3,
            orientation=0,  # North-facing
            year_built=2000,
            timezone="America/New_York"
        )
    
    def test_initialization(self):
        """Test that Building initializes with correct default values."""
        self.assertEqual(self.building.name, "Test Building")
        self.assertEqual(self.building.location, "New York, NY")
        self.assertEqual(self.building.latitude, 40.7128)
        self.assertEqual(self.building.longitude, -74.0060)
        self.assertEqual(self.building.floor_area, 50000)
        self.assertEqual(self.building.num_floors, 3)
        self.assertEqual(self.building.orientation, 0)
        self.assertEqual(self.building.year_built, 2000)
        self.assertEqual(self.building.timezone, "America/New_York")
        self.assertEqual(len(self.building.air_handling_units), 0)
        self.assertEqual(len(self.building.zones), 0)
        self.assertEqual(self.building.outdoor_temp, 70)  # Default temp
        self.assertIsNone(self.building.simulation_time)
        
    def test_add_equipment(self):
        """Test adding HVAC equipment to the building."""
        # Create and add a VAV box
        vav = VAVBox(
            name="Zone1",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
            window_area=80,
            window_orientation="east"
        )
        
        self.building.add_zone(vav)
        self.assertEqual(len(self.building.zones), 1)
        self.assertIn("Zone1", self.building.zone_names)
        
        # Create and add an AHU
        ahu = AirHandlingUnit(
            name="AHU-1",
            cooling_type="chilled_water",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=5000,
            vav_boxes=[vav]
        )
        
        self.building.add_air_handling_unit(ahu)
        self.assertEqual(len(self.building.air_handling_units), 1)
        self.assertIn("AHU-1", self.building.ahu_names)
    
    def test_set_outdoor_conditions(self):
        """Test setting outdoor conditions for the building."""
        # Set outdoor temperature and humidity
        self.building.set_outdoor_conditions(
            temperature=85,
            humidity=60,
            wind_speed=5,
            wind_direction=180,
            solar_ghi=800,
            solar_dni=650,
            solar_dhi=150,
            cloud_cover=30
        )
        
        # Check that values were set
        self.assertEqual(self.building.outdoor_temp, 85)
        self.assertEqual(self.building.outdoor_humidity, 60)
        self.assertEqual(self.building.wind_speed, 5)
        self.assertEqual(self.building.wind_direction, 180)
        self.assertEqual(self.building.solar_ghi, 800)
        self.assertEqual(self.building.solar_dni, 650)
        self.assertEqual(self.building.solar_dhi, 150)
        self.assertEqual(self.building.cloud_cover, 30)
    
    def test_set_time(self):
        """Test setting simulation time."""
        test_time = datetime(2023, 7, 15, 14, 30)  # July 15, 2023, 2:30 PM
        self.building.set_time(test_time)
        
        self.assertEqual(self.building.simulation_time, test_time)
        
        # Test time tuple access
        hour, minute = self.building.get_time_of_day()
        self.assertEqual(hour, 14)
        self.assertEqual(minute, 30)
        
        # Test day of year
        self.assertEqual(self.building.get_day_of_year(), 196)  # July 15 is day 196
    
    def test_update_equipment(self):
        """Test updating all equipment in the building."""
        # Add some equipment
        vav1 = VAVBox(
            name="Office1",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True
        )
        
        vav2 = VAVBox(
            name="Office2",
            min_airflow=150,
            max_airflow=1200,
            zone_temp_setpoint=70,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True
        )
        
        self.building.add_zone(vav1)
        self.building.add_zone(vav2)
        
        ahu = AirHandlingUnit(
            name="AHU-1",
            cooling_type="chilled_water",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=5000,
            vav_boxes=[vav1, vav2]
        )
        
        self.building.add_air_handling_unit(ahu)
        
        # Set zone temps and update
        zone_temps = {
            "Office1": 74,
            "Office2": 68
        }
        
        self.building.set_zone_temperatures(zone_temps)
        self.building.set_outdoor_conditions(temperature=85)
        self.building.update_equipment()
        
        # Verify equipment was updated
        self.assertEqual(vav1.zone_temp, 74)
        self.assertEqual(vav2.zone_temp, 68)
        self.assertEqual(ahu.outdoor_temp, 85)
        
        # Verify cooling is active
        self.assertGreater(ahu.cooling_valve_position, 0)
    
    def test_calculate_solar_position(self):
        """Test calculation of solar position based on time and location."""
        # Set time to noon on summer solstice
        test_time = datetime(2023, 6, 21, 12, 0)
        self.building.set_time(test_time)
        
        # Calculate solar position
        solar_position = self.building.calculate_solar_position()
        
        # Check that we have altitude and azimuth
        self.assertIn("altitude", solar_position)
        self.assertIn("azimuth", solar_position)
        
        # At noon in summer, sun should be reasonably high in sky
        self.assertGreater(solar_position["altitude"], 20)  # Reasonably high in sky for summer
        # The azimuth will vary more widely with location and time of year, so we'll just check it exists
        self.assertGreaterEqual(solar_position["azimuth"], 0)
        self.assertLessEqual(solar_position["azimuth"], 360)
        
        # Test at different time (early morning)
        self.building.set_time(datetime(2023, 6, 21, 6, 0))
        morning_position = self.building.calculate_solar_position()
        
        # Morning sun should be lower in the sky
        self.assertLess(morning_position["altitude"], 30)
        # Just make sure azimuth is a reasonable value
        self.assertGreaterEqual(morning_position["azimuth"], 0)
        self.assertLessEqual(morning_position["azimuth"], 360)
    
    def test_calculate_building_energy(self):
        """Test calculation of total building energy usage."""
        # Add equipment with known energy usage
        vav1 = VAVBox(
            name="Zone1",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True
        )
        
        vav2 = VAVBox(
            name="Zone2",
            min_airflow=150,
            max_airflow=1200,
            zone_temp_setpoint=70,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True
        )
        
        self.building.add_zone(vav1)
        self.building.add_zone(vav2)
        
        ahu1 = AirHandlingUnit(
            name="AHU-1",
            cooling_type="chilled_water",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=3000,
            vav_boxes=[vav1]
        )
        
        ahu2 = AirHandlingUnit(
            name="AHU-2",
            cooling_type="dx",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=3000,
            vav_boxes=[vav2]
        )
        
        self.building.add_air_handling_unit(ahu1)
        self.building.add_air_handling_unit(ahu2)
        
        # Set conditions for energy calculation
        zone_temps = {
            "Zone1": 76,
            "Zone2": 76
        }
        
        self.building.set_zone_temperatures(zone_temps)
        self.building.set_outdoor_conditions(temperature=95)
        self.building.update_equipment()
        
        # Calculate total building energy
        energy = self.building.calculate_total_energy()
        
        # Check that we have totals for each energy type
        self.assertIn("cooling", energy)
        self.assertIn("heating", energy)
        self.assertIn("fan", energy)
        self.assertIn("total", energy)
        
        # Values should be positive
        self.assertGreater(energy["cooling"], 0)
        self.assertGreater(energy["fan"], 0)
        
        # Total should equal the sum of components
        expected_total = energy["cooling"] + energy["heating"] + energy["fan"]
        self.assertAlmostEqual(energy["total"], expected_total)
        
        # Should match sum of individual equipment energies
        ahu1_energy = ahu1.calculate_energy_usage()
        ahu2_energy = ahu2.calculate_energy_usage()
        expected_cooling = ahu1_energy["cooling"] + ahu2_energy["cooling"]
        self.assertAlmostEqual(energy["cooling"], expected_cooling)
    
    def test_run_simulation_step(self):
        """Test running a single simulation step."""
        # Add equipment
        vav = VAVBox(
            name="Office",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
            window_area=80,
            window_orientation="south"
        )
        
        self.building.add_zone(vav)
        
        ahu = AirHandlingUnit(
            name="AHU-1",
            cooling_type="chilled_water",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=5000,
            vav_boxes=[vav]
        )
        
        self.building.add_air_handling_unit(ahu)
        
        # Set initial conditions
        start_time = datetime(2023, 7, 15, 12, 0)
        self.building.set_time(start_time)
        self.building.set_outdoor_conditions(temperature=85, solar_ghi=800)
        self.building.set_zone_temperatures({"Office": 74})
        
        # Record initial state
        initial_temp = vav.zone_temp
        
        # Run simulation for 15 minutes
        result = self.building.run_simulation_step(15)
        
        # Time should have advanced
        self.assertEqual(self.building.simulation_time, start_time + timedelta(minutes=15))
        
        # Zone temperature should have changed
        self.assertNotEqual(vav.zone_temp, initial_temp)
        
        # Result should contain simulation data
        self.assertIn("time", result)
        self.assertIn("outdoor_temp", result)
        self.assertIn("zone_temps", result)
        self.assertIn("energy", result)
    
    def test_simulation_with_weather_data(self):
        """Test simulation using provided weather data."""
        # Add equipment
        vav = VAVBox(
            name="Office",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
            window_area=80,
            window_orientation="south"
        )
        
        self.building.add_zone(vav)
        
        ahu = AirHandlingUnit(
            name="AHU-1",
            cooling_type="chilled_water",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=5000,
            vav_boxes=[vav]
        )
        
        self.building.add_air_handling_unit(ahu)
        
        # Create some sample weather data
        weather_data = [
            {"time": datetime(2023, 7, 15, 12, 0), "temperature": 85, "humidity": 60, "solar_ghi": 800},
            {"time": datetime(2023, 7, 15, 12, 15), "temperature": 86, "humidity": 58, "solar_ghi": 820},
            {"time": datetime(2023, 7, 15, 12, 30), "temperature": 87, "humidity": 57, "solar_ghi": 830},
            {"time": datetime(2023, 7, 15, 12, 45), "temperature": 87, "humidity": 56, "solar_ghi": 840},
            {"time": datetime(2023, 7, 15, 13, 0), "temperature": 88, "humidity": 55, "solar_ghi": 850}
        ]
        
        # Run simulation with weather data
        results = self.building.run_simulation(
            weather_data=weather_data,
            interval_minutes=15,
            initial_zone_temps={"Office": 74}
        )
        
        # Check that we have results for each time step
        self.assertEqual(len(results), len(weather_data))
        
        # Check that outdoor conditions match weather data input
        for i, data in enumerate(weather_data):
            self.assertEqual(results[i]["time"], data["time"])
            self.assertEqual(results[i]["outdoor_temp"], data["temperature"])
        
        # Zone temperatures should change over time
        zone_temps = [result["zone_temps"]["Office"] for result in results]
        self.assertNotEqual(min(zone_temps), max(zone_temps))
    
    def test_energy_report(self):
        """Test generating an energy report for the building."""
        # Add equipment with known energy usage
        vav1 = VAVBox(
            name="Office",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True
        )
        
        vav2 = VAVBox(
            name="Conference",
            min_airflow=150,
            max_airflow=1200,
            zone_temp_setpoint=70,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True
        )
        
        self.building.add_zone(vav1)
        self.building.add_zone(vav2)
        
        ahu1 = AirHandlingUnit(
            name="AHU-1",
            cooling_type="chilled_water",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=3000,
            vav_boxes=[vav1]
        )
        
        ahu2 = AirHandlingUnit(
            name="AHU-2",
            cooling_type="dx",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=3000,
            vav_boxes=[vav2]
        )
        
        self.building.add_air_handling_unit(ahu1)
        self.building.add_air_handling_unit(ahu2)
        
        # Set conditions and run simulation steps
        weather_data = [
            {"time": datetime(2023, 7, 15, 12, 0), "temperature": 85, "humidity": 60, "solar_ghi": 800},
            {"time": datetime(2023, 7, 15, 12, 15), "temperature": 86, "humidity": 58, "solar_ghi": 820},
            {"time": datetime(2023, 7, 15, 12, 30), "temperature": 87, "humidity": 57, "solar_ghi": 830}
        ]
        
        # Run simulation to generate data
        results = self.building.run_simulation(
            weather_data=weather_data,
            interval_minutes=15,
            initial_zone_temps={"Office": 74, "Conference": 72}
        )
        
        # Generate energy report
        report = self.building.generate_energy_report(results)
        
        # Check that report has expected sections
        self.assertIn("total_energy", report)
        self.assertIn("energy_by_type", report)
        self.assertIn("energy_by_equipment", report)
        self.assertIn("peak_demand", report)
        
        # Energy by type should include cooling, heating, and fan
        self.assertIn("cooling", report["energy_by_type"])
        self.assertIn("heating", report["energy_by_type"])
        self.assertIn("fan", report["energy_by_type"])
        
        # Energy by equipment should include both AHUs
        self.assertIn("AHU-1", report["energy_by_equipment"])
        self.assertIn("AHU-2", report["energy_by_equipment"])
        
        # Check that total energy is positive and matches sum of components
        self.assertGreater(report["total_energy"], 0)
        component_sum = sum(report["energy_by_type"].values())
        self.assertAlmostEqual(report["total_energy"], component_sum)
        
    def test_get_process_variables(self):
        """Test that Building returns a dictionary of all process variables."""
        # Add some equipment
        vav = VAVBox(
            name="Zone1",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True
        )
        
        self.building.add_zone(vav)
        
        ahu = AirHandlingUnit(
            name="AHU-1",
            cooling_type="chilled_water",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=5000,
            vav_boxes=[vav]
        )
        
        self.building.add_air_handling_unit(ahu)
        
        # Set time and conditions
        self.building.set_time(datetime(2023, 7, 15, 12, 0))
        self.building.set_outdoor_conditions(
            temperature=85, 
            humidity=60, 
            solar_ghi=800, 
            wind_speed=5, 
            wind_direction=180
        )
        self.building.set_zone_temperatures({"Zone1": 74})
        self.building.update_equipment()
        
        # Get process variables
        variables = self.building.get_process_variables()
        
        # Check that it's a dictionary
        self.assertIsInstance(variables, dict)
        
        # Check that it contains essential state variables
        essential_vars = [
            "name", "location", "latitude", "longitude", 
            "outdoor_temp", "outdoor_humidity", "wind_speed", "wind_direction",
            "solar_altitude", "solar_azimuth", "ahu_names", "zone_names", 
            "zone_temps", "energy"
        ]
        
        for var in essential_vars:
            self.assertIn(var, variables)
            
        # Check that values match the actual object properties
        self.assertEqual(variables["name"], self.building.name)
        self.assertEqual(variables["location"], self.building.location)
        self.assertEqual(variables["outdoor_temp"], self.building.outdoor_temp)
        self.assertEqual(variables["outdoor_humidity"], self.building.outdoor_humidity)
        
        # Check equipment lists
        self.assertEqual(variables["ahu_names"], self.building.ahu_names)
        self.assertEqual(variables["zone_names"], self.building.zone_names)
        
        # Check zone temperatures
        self.assertEqual(variables["zone_temps"]["Zone1"], 74)
        
        # Check energy calculation
        self.assertIsInstance(variables["energy"], dict)
        self.assertIn("cooling", variables["energy"])
        self.assertIn("heating", variables["energy"])
        self.assertIn("fan", variables["energy"])
        self.assertIn("total", variables["energy"])

if __name__ == '__main__':
    unittest.main()
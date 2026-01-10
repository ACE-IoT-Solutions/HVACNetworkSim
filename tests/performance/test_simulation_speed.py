"""Performance tests for HVAC simulation speed and memory usage.

These tests benchmark the simulation with various configurations to ensure
acceptable performance as the system scales.
"""

import time
import pytest

from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
from src.chiller import Chiller
from src.cooling_tower import CoolingTower
from src.boiler import Boiler


class TestVAVPerformance:
    """Performance tests for VAV box operations."""

    def test_single_vav_update_speed(self):
        """Test that a single VAV update completes quickly."""
        vav = VAVBox(
            name="VAV-Perf",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
        )

        # Warm up
        vav.update(zone_temp=74, supply_air_temp=55)

        # Time 1000 updates
        start = time.perf_counter()
        for _ in range(1000):
            vav.update(zone_temp=74, supply_air_temp=55)
        elapsed = time.perf_counter() - start

        # Should complete 1000 updates in under 100ms
        assert elapsed < 0.1, f"1000 VAV updates took {elapsed:.3f}s (expected < 0.1s)"

    def test_vav_thermal_calculation_speed(self):
        """Test thermal behavior calculation performance."""
        vav = VAVBox(
            name="VAV-Thermal-Perf",
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

        # Warm up
        vav.calculate_thermal_behavior(
            minutes=15, outdoor_temp=85, vav_cooling_effect=0.5, time_of_day=(12, 0)
        )

        # Time 1000 thermal calculations
        start = time.perf_counter()
        for _ in range(1000):
            vav.calculate_thermal_behavior(
                minutes=15, outdoor_temp=85, vav_cooling_effect=0.5, time_of_day=(12, 0)
            )
        elapsed = time.perf_counter() - start

        # Should complete 1000 calculations in under 50ms
        assert elapsed < 0.05, f"1000 thermal calcs took {elapsed:.3f}s (expected < 0.05s)"


class TestAHUPerformance:
    """Performance tests for AHU operations."""

    @pytest.fixture
    def ahu_with_vavs(self):
        """Create AHU with multiple VAV boxes."""
        vavs = [
            VAVBox(
                name=f"VAV-{i}",
                min_airflow=100,
                max_airflow=800,
                zone_temp_setpoint=72,
                deadband=2,
                discharge_air_temp_setpoint=55,
                has_reheat=True,
            )
            for i in range(1, 11)  # 10 VAVs
        ]

        ahu = AirHandlingUnit(
            name="AHU-Perf",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=10000,
            vav_boxes=vavs,
            enable_supply_temp_reset=True,
        )
        return ahu

    def test_ahu_with_10_vavs_update_speed(self, ahu_with_vavs):
        """Test AHU update with 10 VAV boxes."""
        zone_temps = {f"VAV-{i}": 72 + (i % 5) for i in range(1, 11)}

        # Warm up
        ahu_with_vavs.update(zone_temps, outdoor_temp=85)

        # Time 100 updates
        start = time.perf_counter()
        for _ in range(100):
            ahu_with_vavs.update(zone_temps, outdoor_temp=85)
        elapsed = time.perf_counter() - start

        # Should complete 100 AHU updates (with 10 VAVs each) in under 100ms
        assert elapsed < 0.1, f"100 AHU updates took {elapsed:.3f}s (expected < 0.1s)"


class TestScalePerformance:
    """Performance tests for scaled-up simulations."""

    def test_100_vav_creation_speed(self):
        """Test that creating 100 VAV boxes is fast."""
        start = time.perf_counter()
        vavs = [
            VAVBox(
                name=f"VAV-{i}",
                min_airflow=100,
                max_airflow=800,
                zone_temp_setpoint=72,
                deadband=2,
                discharge_air_temp_setpoint=55,
                has_reheat=True,
                zone_area=400,
                zone_volume=3200,
            )
            for i in range(100)
        ]
        elapsed = time.perf_counter() - start

        assert len(vavs) == 100
        # Should create 100 VAVs in under 500ms
        assert elapsed < 0.5, f"Creating 100 VAVs took {elapsed:.3f}s (expected < 0.5s)"

    def test_100_vav_update_speed(self):
        """Test updating 100 VAV boxes."""
        vavs = [
            VAVBox(
                name=f"VAV-{i}",
                min_airflow=100,
                max_airflow=800,
                zone_temp_setpoint=72,
                deadband=2,
                discharge_air_temp_setpoint=55,
                has_reheat=True,
            )
            for i in range(100)
        ]

        # Warm up
        for vav in vavs:
            vav.update(zone_temp=74, supply_air_temp=55)

        # Time 10 full update cycles (1000 individual VAV updates)
        start = time.perf_counter()
        for _ in range(10):
            for vav in vavs:
                vav.update(zone_temp=74, supply_air_temp=55)
        elapsed = time.perf_counter() - start

        # Should complete 1000 VAV updates in under 200ms
        assert elapsed < 0.2, f"1000 VAV updates took {elapsed:.3f}s (expected < 0.2s)"

    def test_multiple_ahu_with_vavs(self):
        """Test multiple AHUs each with multiple VAVs."""
        ahus = []
        for ahu_idx in range(5):
            vavs = [
                VAVBox(
                    name=f"AHU{ahu_idx}-VAV-{i}",
                    min_airflow=100,
                    max_airflow=800,
                    zone_temp_setpoint=72,
                    deadband=2,
                    discharge_air_temp_setpoint=55,
                    has_reheat=True,
                )
                for i in range(20)  # 20 VAVs per AHU
            ]
            ahu = AirHandlingUnit(
                name=f"AHU-{ahu_idx}",
                supply_air_temp_setpoint=55,
                min_supply_air_temp=52,
                max_supply_air_temp=65,
                max_supply_airflow=20000,
                vav_boxes=vavs,
            )
            ahus.append(ahu)

        # 5 AHUs x 20 VAVs = 100 total VAVs

        # Time 10 update cycles
        start = time.perf_counter()
        for _ in range(10):
            for ahu_idx, ahu in enumerate(ahus):
                zone_temps = {f"AHU{ahu_idx}-VAV-{i}": 72 + (i % 5) for i in range(20)}
                ahu.update(zone_temps, outdoor_temp=85)
        elapsed = time.perf_counter() - start

        # Should complete 50 AHU updates (500 VAV updates) in under 200ms
        assert elapsed < 0.2, f"50 AHU updates took {elapsed:.3f}s (expected < 0.2s)"


class TestChillerPlantPerformance:
    """Performance tests for chiller plant operations."""

    @pytest.fixture
    def chiller_plant(self):
        """Create a chiller with cooling tower."""
        tower = CoolingTower(
            name="CT-Perf",
            capacity=600,
            design_approach=7,
            design_range=10,
            design_wet_bulb=78,
            min_speed=20,
            tower_type="counterflow",
            fan_power=50,
            num_cells=1,
        )

        chiller = Chiller(
            name="Chiller-Perf",
            cooling_type="water_cooled",
            capacity=500,
            design_cop=5.0,
            design_entering_condenser_temp=85,
            design_leaving_chilled_water_temp=44,
            min_part_load_ratio=0.1,
            design_chilled_water_flow=1000,
            design_condenser_water_flow=1200,
        )
        chiller.connect_cooling_tower(tower)
        return chiller

    def test_chiller_update_speed(self, chiller_plant):
        """Test chiller update performance."""
        # Warm up
        chiller_plant.update_load(
            load=300,
            entering_chilled_water_temp=54,
            chilled_water_flow=800,
            ambient_wet_bulb=75,
        )

        # Time 1000 updates
        start = time.perf_counter()
        for i in range(1000):
            load = 200 + (i % 300)  # Vary load
            chiller_plant.update_load(
                load=load,
                entering_chilled_water_temp=54,
                chilled_water_flow=800,
                ambient_wet_bulb=75,
            )
        elapsed = time.perf_counter() - start

        # Should complete 1000 chiller updates in under 100ms
        assert elapsed < 0.1, f"1000 chiller updates took {elapsed:.3f}s (expected < 0.1s)"


class TestBoilerPerformance:
    """Performance tests for boiler operations."""

    @pytest.fixture
    def boiler(self):
        """Create a boiler for testing."""
        return Boiler(
            name="Boiler-Perf",
            fuel_type="gas",
            capacity=1000,
            design_efficiency=0.85,
            design_entering_water_temp=160,
            design_leaving_water_temp=180,
            min_part_load_ratio=0.2,
            design_hot_water_flow=100,
            condensing=False,
            turndown_ratio=4.0,
        )

    def test_boiler_update_speed(self, boiler):
        """Test boiler update performance."""
        # Warm up
        boiler.update_load(
            load=500,
            entering_water_temp=160,
            hot_water_flow=80,
            ambient_temp=70,
        )

        # Time 1000 updates
        start = time.perf_counter()
        for i in range(1000):
            load = 300 + (i % 500)  # Vary load
            boiler.update_load(
                load=load,
                entering_water_temp=160,
                hot_water_flow=80,
                ambient_temp=70,
            )
        elapsed = time.perf_counter() - start

        # Should complete 1000 boiler updates in under 100ms
        assert elapsed < 0.1, f"1000 boiler updates took {elapsed:.3f}s (expected < 0.1s)"


class TestMemoryUsage:
    """Tests for memory efficiency."""

    def test_vav_memory_footprint(self):
        """Test that VAV boxes have reasonable memory footprint."""
        import sys

        vav = VAVBox(
            name="VAV-Memory",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
        )

        # Get approximate size (this is a rough estimate)
        size = sys.getsizeof(vav) + sys.getsizeof(vav.__dict__)

        # VAV should be under 2KB base size
        assert size < 2048, f"VAV memory footprint is {size} bytes (expected < 2048)"

    def test_large_scale_memory(self):
        """Test memory usage with many objects."""
        import gc

        gc.collect()

        # Create 500 VAVs
        vavs = [
            VAVBox(
                name=f"VAV-{i}",
                min_airflow=100,
                max_airflow=800,
                zone_temp_setpoint=72,
                deadband=2,
                discharge_air_temp_setpoint=55,
                has_reheat=True,
            )
            for i in range(500)
        ]

        assert len(vavs) == 500

        # Clean up
        del vavs
        gc.collect()


class TestSimulationThroughput:
    """Tests for overall simulation throughput."""

    def test_one_hour_simulation_speed(self):
        """Test simulating one hour of building operation."""
        # Create a small building: 1 AHU with 10 VAVs
        vavs = [
            VAVBox(
                name=f"VAV-{i}",
                min_airflow=100,
                max_airflow=800,
                zone_temp_setpoint=72,
                deadband=2,
                discharge_air_temp_setpoint=55,
                has_reheat=True,
                zone_area=400,
                zone_volume=3200,
                thermal_mass=2.0,
            )
            for i in range(10)
        ]

        ahu = AirHandlingUnit(
            name="AHU-Sim",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=10000,
            vav_boxes=vavs,
            enable_supply_temp_reset=True,
        )

        # Simulate 60 minutes (1-minute time steps)
        zone_temps = {f"VAV-{i}": 72.0 for i in range(10)}

        start = time.perf_counter()
        for minute in range(60):
            # Update AHU and all VAVs
            ahu.update(zone_temps, outdoor_temp=85)

            # Update zone temperatures based on thermal behavior
            for i, vav in enumerate(vavs):
                temp_change = vav.calculate_thermal_behavior(
                    minutes=1,
                    outdoor_temp=85,
                    vav_cooling_effect=vav.damper_position,
                    time_of_day=(12, minute),
                )
                zone_temps[f"VAV-{i}"] = vav.zone_temp + temp_change

        elapsed = time.perf_counter() - start

        # Should simulate 1 hour in under 100ms
        assert elapsed < 0.1, f"1-hour simulation took {elapsed:.3f}s (expected < 0.1s)"

    def test_day_simulation_speed(self):
        """Test simulating a full day of building operation."""
        # Create a medium building: 2 AHUs with 10 VAVs each
        ahus = []
        all_vavs = {}

        for ahu_idx in range(2):
            vavs = [
                VAVBox(
                    name=f"AHU{ahu_idx}-VAV-{i}",
                    min_airflow=100,
                    max_airflow=800,
                    zone_temp_setpoint=72,
                    deadband=2,
                    discharge_air_temp_setpoint=55,
                    has_reheat=True,
                )
                for i in range(10)
            ]

            ahu = AirHandlingUnit(
                name=f"AHU-{ahu_idx}",
                supply_air_temp_setpoint=55,
                min_supply_air_temp=52,
                max_supply_air_temp=65,
                max_supply_airflow=10000,
                vav_boxes=vavs,
            )
            ahus.append(ahu)

            for i in range(10):
                all_vavs[f"AHU{ahu_idx}-VAV-{i}"] = 72.0

        # Simulate 24 hours with 15-minute time steps (96 steps)
        start = time.perf_counter()
        for step in range(96):
            hour = (step * 15) // 60

            # Vary outdoor temp by time of day
            outdoor_temp = 70 + 15 * (1 - abs(hour - 14) / 14)

            for ahu_idx, ahu in enumerate(ahus):
                zone_temps = {
                    f"AHU{ahu_idx}-VAV-{i}": all_vavs[f"AHU{ahu_idx}-VAV-{i}"] for i in range(10)
                }
                ahu.update(zone_temps, outdoor_temp=outdoor_temp)

        elapsed = time.perf_counter() - start

        # Should simulate 24 hours (96 steps, 20 VAVs) in under 200ms
        assert elapsed < 0.2, f"24-hour simulation took {elapsed:.3f}s (expected < 0.2s)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

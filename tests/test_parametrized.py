"""Parametrized tests for HVAC equipment behavior.

Uses pytest.mark.parametrize to test equipment across various conditions.
"""

import pytest

from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
from src.chiller import Chiller
from src.cooling_tower import CoolingTower
from src.boiler import Boiler


class TestVAVModeSelection:
    """Parametrized tests for VAV box mode selection."""

    @pytest.fixture
    def vav(self):
        """Create a standard VAV box for testing."""
        return VAVBox(
            name="Test-VAV",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
        )

    @pytest.mark.parametrize(
        "zone_temp,expected_mode",
        [
            (78, "cooling"),  # Well above setpoint + deadband
            (76, "cooling"),  # Above setpoint + 1/2 deadband
            (74, "cooling"),  # Just above setpoint + 1/2 deadband
            (73, "deadband"),  # Within deadband
            (72, "deadband"),  # At setpoint
            (71, "deadband"),  # Just below setpoint
            (70, "heating"),  # At setpoint - 1/2 deadband
            (68, "heating"),  # Below setpoint - deadband
            (65, "heating"),  # Well below setpoint
        ],
    )
    def test_vav_mode_from_zone_temp(self, vav, zone_temp, expected_mode):
        """Test VAV mode selection based on zone temperature."""
        vav.update(zone_temp=zone_temp, supply_air_temp=55)
        assert vav.mode == expected_mode

    @pytest.mark.parametrize(
        "zone_temp,expected_airflow_range",
        [
            (68, (100, 200)),  # Heating - minimum airflow
            (72, (100, 200)),  # Deadband - minimum airflow
            (76, (500, 1000)),  # Moderate cooling - medium airflow
            (80, (900, 1000)),  # High cooling - near max airflow
        ],
    )
    def test_vav_airflow_from_zone_temp(self, vav, zone_temp, expected_airflow_range):
        """Test VAV airflow modulation based on zone temperature."""
        vav.update(zone_temp=zone_temp, supply_air_temp=55)
        assert expected_airflow_range[0] <= vav.current_airflow <= expected_airflow_range[1]


class TestAHUSupplyTempReset:
    """Parametrized tests for AHU supply temperature reset."""

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
            for i in range(1, 4)
        ]

        ahu = AirHandlingUnit(
            name="AHU-Test",
            supply_air_temp_setpoint=55,
            min_supply_air_temp=52,
            max_supply_air_temp=65,
            max_supply_airflow=3000,
            vav_boxes=vavs,
            enable_supply_temp_reset=True,
        )
        return ahu

    @pytest.mark.parametrize(
        "zone_temps,outdoor_temp,expected_sat_range",
        [
            # All zones cooling - supply should be low
            ({"VAV-1": 76, "VAV-2": 77, "VAV-3": 78}, 90, (52, 56)),
            # Mixed zones - supply should be moderate
            ({"VAV-1": 74, "VAV-2": 72, "VAV-3": 70}, 70, (54, 62)),
            # All zones heating - supply should be high
            ({"VAV-1": 68, "VAV-2": 67, "VAV-3": 66}, 35, (58, 65)),
        ],
    )
    def test_supply_temp_reset(self, ahu_with_vavs, zone_temps, outdoor_temp, expected_sat_range):
        """Test AHU supply temperature reset based on zone demands."""
        ahu_with_vavs.update(zone_temps, outdoor_temp=outdoor_temp)
        assert (
            expected_sat_range[0] <= ahu_with_vavs.current_supply_air_temp <= expected_sat_range[1]
        )


class TestChillerPerformance:
    """Parametrized tests for chiller performance."""

    @pytest.fixture
    def chiller_with_tower(self):
        """Create water-cooled chiller with cooling tower."""
        tower = CoolingTower(
            name="CT-Test",
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
            name="Chiller-Test",
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

    @pytest.mark.parametrize(
        "load,wet_bulb,expected_cop_range",
        [
            # Lower load, lower wet bulb = higher COP
            (250, 65, (4.5, 6.5)),
            # Design conditions
            (400, 78, (4.0, 5.5)),
            # High load, high wet bulb = lower COP
            (480, 82, (3.5, 5.0)),
        ],
    )
    def test_chiller_cop_at_conditions(
        self, chiller_with_tower, load, wet_bulb, expected_cop_range
    ):
        """Test chiller COP varies with load and wet bulb."""
        chiller_with_tower.update_load(
            load=load,
            entering_chilled_water_temp=54,
            chilled_water_flow=800,
            ambient_wet_bulb=wet_bulb,
        )
        assert expected_cop_range[0] <= chiller_with_tower.current_cop <= expected_cop_range[1]


class TestBoilerEfficiency:
    """Parametrized tests for boiler efficiency."""

    @pytest.fixture
    def gas_boiler(self):
        """Create gas boiler for testing."""
        return Boiler(
            name="Boiler-Test",
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

    @pytest.mark.parametrize(
        "load,expected_efficiency_range",
        [
            # Low load (at turndown)
            (250, (0.70, 0.92)),
            # Medium load
            (500, (0.80, 0.92)),
            # High load (efficiency may be slightly below design at higher temps)
            (900, (0.80, 0.92)),
        ],
    )
    def test_boiler_efficiency_at_load(self, gas_boiler, load, expected_efficiency_range):
        """Test boiler efficiency varies with load."""
        gas_boiler.update_load(
            load=load,
            entering_water_temp=160,
            hot_water_flow=80,
            ambient_temp=70,
        )
        assert (
            expected_efficiency_range[0]
            <= gas_boiler.current_efficiency
            <= expected_efficiency_range[1]
        )


class TestCoolingTowerPerformance:
    """Parametrized tests for cooling tower performance."""

    @pytest.fixture
    def cooling_tower(self):
        """Create cooling tower for testing."""
        return CoolingTower(
            name="CT-Test",
            capacity=600,
            design_approach=7,
            design_range=10,
            design_wet_bulb=78,
            min_speed=20,
            tower_type="counterflow",
            fan_power=50,
            num_cells=1,
        )

    @pytest.mark.parametrize(
        "load,wet_bulb,expected_approach_range",
        [
            # Low load, low wet bulb - approach should be good (can go very low)
            (200, 65, (2, 12)),
            # Design conditions
            (600, 78, (6, 10)),
            # High conditions - approach may increase
            (550, 80, (7, 15)),
        ],
    )
    def test_cooling_tower_approach(self, cooling_tower, load, wet_bulb, expected_approach_range):
        """Test cooling tower approach temperature at various conditions."""
        cooling_tower.update_load(
            load=load,
            entering_water_temp=95,
            ambient_wet_bulb=wet_bulb,
            condenser_water_flow=1200,
        )
        assert (
            expected_approach_range[0]
            <= cooling_tower.current_approach
            <= expected_approach_range[1]
        )


class TestThermalBehavior:
    """Parametrized tests for zone thermal behavior."""

    @pytest.fixture
    def vav_with_zone(self):
        """Create VAV with thermal zone for testing."""
        return VAVBox(
            name="VAV-Thermal",
            min_airflow=100,
            max_airflow=1000,
            zone_temp_setpoint=72,
            deadband=2,
            discharge_air_temp_setpoint=55,
            has_reheat=True,
            zone_area=400,
            zone_volume=3200,
            window_area=80,
            window_orientation="east",
            thermal_mass=2.0,
        )

    @pytest.mark.parametrize(
        "time_of_day,window_orientation,expected_gain_range",
        [
            # Morning, east-facing - peak solar gain (peak at 9 AM for east)
            ((8, 0), "east", (10000, 20000)),
            # Noon, east-facing - still significant gain (3 hours from peak)
            ((12, 0), "east", (500, 5000)),
            # Afternoon, west-facing - peak solar gain (peak at 3 PM for west)
            ((16, 0), "west", (10000, 20000)),
            # Morning, west-facing - lower gain (7 hours from peak, but some indirect)
            ((8, 0), "west", (0, 1500)),
            # Night time - minimal gain
            ((22, 0), "east", (0, 10)),
        ],
    )
    def test_solar_gain_by_orientation_and_time(
        self,
        vav_with_zone,
        time_of_day,
        window_orientation,
        expected_gain_range,
    ):
        """Test solar gain varies with orientation and time (BTU/hr)."""
        vav_with_zone.window_orientation = window_orientation

        solar_gain = vav_with_zone.calculate_solar_gain(time_of_day)

        assert expected_gain_range[0] <= solar_gain <= expected_gain_range[1]

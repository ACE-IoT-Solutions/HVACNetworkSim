"""Tests for src/physics/thermal.py"""

import unittest
from src.physics.thermal import (
    calculate_air_mass_flow,
    calculate_sensible_heat,
    calculate_water_heat_transfer,
    calculate_chilled_water_delta_t,
    calculate_chilled_water_flow,
    calculate_fan_power,
    convert_kw_to_btu,
    convert_btu_to_kw,
)


class TestAirCalculations(unittest.TestCase):
    """Tests for air-related thermal calculations."""

    def test_calculate_air_mass_flow(self):
        """Test air mass flow calculation."""
        # 1000 CFM * 0.075 lb/ft³ * 60 min/hr = 4500 lb/hr
        mass_flow = calculate_air_mass_flow(1000)
        self.assertAlmostEqual(mass_flow, 4500.0, places=1)

    def test_calculate_air_mass_flow_zero(self):
        """Test with zero flow."""
        self.assertEqual(calculate_air_mass_flow(0), 0.0)

    def test_calculate_sensible_heat(self):
        """Test sensible heat calculation for air."""
        # 1000 CFM, 20°F delta: 4500 lb/hr * 0.24 BTU/lb·°F * 20°F = 21,600 BTU/hr
        heat = calculate_sensible_heat(1000, 20)
        self.assertAlmostEqual(heat, 21600.0, places=0)

    def test_calculate_sensible_heat_cooling(self):
        """Test cooling calculation (positive delta_t for cooling)."""
        # Typical VAV cooling: 500 CFM, 15°F drop (75 - 55)
        heat = calculate_sensible_heat(500, 15)
        # Expected: 500 * 0.075 * 60 * 0.24 * 15 = 8100 BTU/hr
        self.assertAlmostEqual(heat, 8100.0, places=0)


class TestWaterCalculations(unittest.TestCase):
    """Tests for water-related thermal calculations."""

    def test_calculate_water_heat_transfer(self):
        """Test water heat transfer calculation."""
        # 100 GPM, 10°F delta: 500 * 100 * 10 = 500,000 BTU/hr
        heat = calculate_water_heat_transfer(100, 10)
        self.assertAlmostEqual(heat, 500000.0, places=0)

    def test_calculate_chilled_water_delta_t(self):
        """Test chilled water delta T calculation."""
        # 500,000 BTU/hr, 100 GPM: 500000 / (500 * 100) = 10°F
        delta_t = calculate_chilled_water_delta_t(500000, 100)
        self.assertAlmostEqual(delta_t, 10.0, places=1)

    def test_calculate_chilled_water_delta_t_zero_flow(self):
        """Test with zero flow returns zero."""
        delta_t = calculate_chilled_water_delta_t(500000, 0)
        self.assertEqual(delta_t, 0.0)

    def test_calculate_chilled_water_flow(self):
        """Test chilled water flow calculation."""
        # 500,000 BTU/hr, 10°F delta: 500000 / (500 * 10) = 100 GPM
        flow = calculate_chilled_water_flow(500000, 10)
        self.assertAlmostEqual(flow, 100.0, places=1)

    def test_calculate_chilled_water_flow_zero_delta(self):
        """Test with zero delta returns zero."""
        flow = calculate_chilled_water_flow(500000, 0)
        self.assertEqual(flow, 0.0)


class TestFanPower(unittest.TestCase):
    """Tests for fan power calculations using affinity laws."""

    def test_calculate_fan_power_full_speed(self):
        """Test fan power at full speed."""
        power = calculate_fan_power(1000, 1000, 10.0)
        self.assertAlmostEqual(power, 10.0, places=1)

    def test_calculate_fan_power_half_speed(self):
        """Test fan power at half speed - cube law with minimum floor."""
        # 50% flow → max((0.5)³, 0.3 * 0.5) = max(0.125, 0.15) = 0.15 (15% power)
        power = calculate_fan_power(500, 1000, 10.0)
        self.assertAlmostEqual(power, 1.5, places=1)

    def test_calculate_fan_power_quarter_speed(self):
        """Test fan power at quarter speed."""
        # 25% flow → (0.25)³ = 1.56% power, but min_power_fraction kicks in
        power = calculate_fan_power(250, 1000, 10.0)
        # Expected: max(0.25³, 0.3 * 0.25) * 10 = max(0.0156, 0.075) * 10 = 0.75
        self.assertAlmostEqual(power, 0.75, places=1)

    def test_calculate_fan_power_zero_flow(self):
        """Test fan power with zero flow."""
        power = calculate_fan_power(0, 1000, 10.0)
        self.assertEqual(power, 0.0)


class TestUnitConversions(unittest.TestCase):
    """Tests for unit conversion functions."""

    def test_convert_kw_to_btu(self):
        """Test kW to BTU/hr conversion."""
        # 1 kW = 3412 BTU/hr
        btu = convert_kw_to_btu(1.0)
        self.assertAlmostEqual(btu, 3412.0, places=0)

    def test_convert_btu_to_kw(self):
        """Test BTU/hr to kW conversion."""
        kw = convert_btu_to_kw(3412.0)
        self.assertAlmostEqual(kw, 1.0, places=2)

    def test_round_trip_conversion(self):
        """Test that kW → BTU → kW is consistent."""
        original_kw = 5.5
        btu = convert_kw_to_btu(original_kw)
        result_kw = convert_btu_to_kw(btu)
        self.assertAlmostEqual(result_kw, original_kw, places=5)


if __name__ == "__main__":
    unittest.main()

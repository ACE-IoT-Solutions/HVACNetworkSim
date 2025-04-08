# HVAC Network Simulation

This project simulates HVAC components, including VAV boxes, Air Handling Units (AHUs), and complete buildings.

## Components

- **VAV Box**: Variable Air Volume terminal unit with optional reheat capability
  - Modulates airflow in cooling mode
  - Controls reheat valve in heating mode
  - Maintains minimum airflow in deadband mode
  - Calculates energy usage
  - Models thermal behavior with occupancy and solar heat gain
  - Supports time-of-day simulation

- **Air Handling Unit (AHU)**: Central unit that supplies conditioned air to multiple VAV boxes
  - Controls supply air temperature
  - Coordinates multiple VAV boxes
  - Manages cooling and heating coil valve positions
  - Calculates total system energy usage
  - Optional supply air temperature reset for energy savings
  - Supports both chilled water and DX (direct expansion) cooling
  - Calculates chilled water flow rates for hydronic systems
  - Models multi-stage compressor operation for DX systems
  
- **Building**: Top-level container for HVAC equipment and building-wide data
  - Manages multiple AHUs and zones
  - Tracks outdoor weather conditions (temperature, humidity, wind, solar)
  - Calculates solar position based on time and location
  - Models building-wide energy usage
  - Generates energy reports by equipment and energy type
  - Supports time-based simulation with weather data inputs
  
- **Cooling Tower**: Evaporative heat rejection for water-cooled chillers
  - Models part-load performance based on wet bulb and load conditions
  - Calculates approach temperature and efficiency
  - Simulates variable-speed fan control
  - Predicts water consumption from evaporation, drift, and blowdown
  - Supports multiple cells with load-based staging
  
- **Chiller**: Produces chilled water for cooling coils
  - Supports both water-cooled and air-cooled configurations
  - Models COP and capacity based on part-load ratio and temperatures
  - Integrates with cooling tower for water-cooled operation
  - Calculates energy consumption based on operating conditions
  - Allows for setpoint adjustment with efficiency impacts
  
- **Boiler**: Produces hot water for heating coils
  - Supports both gas-fired and electric configurations
  - Models condensing boiler efficiency variation with return water temperature
  - Simulates realistic cycling behavior with minimum run times
  - Calculates fuel consumption with appropriate units
  - Provides detailed energy analysis for different operating modes

## Getting Started

```bash
# Run the tests
python -m unittest discover tests

# Run single VAV box simulation (requires matplotlib)
python example_simulation.py

# Run thermal simulation with solar gain and occupancy (requires matplotlib)
python example_thermal_simulation.py

# Run AHU with multiple VAV boxes simulation (requires matplotlib)
python example_ahu_simulation.py

# Compare chilled water and DX cooling types (requires matplotlib)
python example_cooling_types.py

# Run complete building simulation with weather data (requires matplotlib)
python example_building_simulation.py

# Run comprehensive system simulation with all equipment types (requires matplotlib)
python example_complete_system.py
```

## Features

- Realistic PID control for damper and reheat valve modulation
- Deadband operation to prevent short cycling
- Energy usage calculation for all system components
- Supply air temperature reset based on zone demands
- Dynamic thermal modeling of zone temperatures
- Support for both heating and cooling modes
- Time-of-day based solar heat gain calculation
- Occupancy-based thermal load modeling
- Window orientation effects on zone temperature
- Thermal mass and building envelope heat transfer
- Multiple cooling system types:
  - Chilled water systems with valve modulation and flow calculation
  - DX (direct expansion) systems with multi-stage compressor control
  - Different efficiency models based on system type and conditions
- Central plant equipment:
  - Cooling towers with variable-speed fans and approach temperature modeling
  - Chillers with performance curves and condenser temperature effects
  - Boilers with condensing operation and fuel consumption tracking
  - Primary/secondary equipment integration (chiller + cooling tower)
- Whole-building simulation capabilities:
  - Integration of multiple HVAC systems 
  - Building-level energy analysis and reporting
  - Weather data processing
  - Solar position calculation based on time and location
  - Time-based simulation with variable conditions

## Example Simulations

### Single VAV Box Simulation

The `example_simulation.py` script demonstrates a single VAV box behavior over a 24-hour period with:

- Varying zone temperature based on time of day
- Automatic mode switching between heating, cooling, and deadband
- Visualization of temperatures, airflow, valve positions, and energy usage
- Color-coded operating modes

### Thermal Simulation with Solar and Occupancy

The `example_thermal_simulation.py` script demonstrates thermal behavior of VAV zones with:

- East-facing and west-facing office zones for comparison
- Time-of-day effects on solar heat gain through windows
- Scheduled occupancy with appropriate heat gain from people
- Building envelope heat transfer based on outdoor temperatures
- Detailed thermal modeling showing how zones respond differently throughout the day
- Comparison of HVAC system response to different solar load profiles

### AHU Simulation

The `example_ahu_simulation.py` script demonstrates an AHU controlling multiple VAV boxes:

- Models a small building with office, conference room, and lobby zones
- Realistic occupancy patterns for each zone
- Dynamic thermal model accounting for outdoor conditions and internal loads
- Visualization of all zone temperatures, airflows, and system energy usage
- Supply air temperature reset based on zone demands

### Cooling Types Comparison

The `example_cooling_types.py` script compares different cooling system types:

- Side-by-side comparison of chilled water and DX cooling performance
- Response to varying outdoor temperatures and cooling loads
- Chilled water flow rate calculation based on cooling demand
- DX compressor staging based on load requirements
- Energy efficiency differences between system types
- Impact of outdoor temperature on system performance

### Complete Building Simulation

The `example_building_simulation.py` script demonstrates a whole-building simulation:

- Models a complete 2-story office building with multiple HVAC systems
- 5 thermal zones with different setpoints and orientations
- Mixed equipment types (chilled water and DX cooling systems)
- 24-hour simulation with realistic weather data
- Solar position calculation based on time, date, and location
- Comprehensive energy reporting and visualization
- Analysis of energy consumption by equipment type and category

### Comprehensive System Simulation

The `example_complete_system.py` script demonstrates a complete HVAC system with all equipment types:

- Models a mixed-use 4-story building with multiple HVAC systems
- Includes 14 zones across different space types (office, retail, conference, lobby)
- Multiple AHUs with both chilled water and DX cooling
- Diverse central plant equipment:
  - Water-cooled and air-cooled chillers
  - Cooling towers with variable-speed fans
  - Gas-fired condensing and electric boilers
- Load distribution between parallel equipment
- Performance monitoring of all system components
- Analysis of efficiency under varying conditions
- Detailed visualization of key performance metrics
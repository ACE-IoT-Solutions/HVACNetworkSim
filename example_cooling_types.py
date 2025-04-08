#!/usr/bin/env python
"""
Example simulation comparing chilled water and DX cooling AHUs.
This simulates two identical building zones served by different AHU types.
"""

import math
import time
from src.vav_box import VAVBox
from src.ahu import AirHandlingUnit
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta

def main():
    # Create identical VAV boxes for both systems
    vav_boxes = []
    for i in range(5):
        vav = VAVBox(
            name=f"Zone{i+1}",
            min_airflow=150,  # CFM
            max_airflow=1200,  # CFM
            zone_temp_setpoint=72,  # °F
            deadband=2,  # °F
            discharge_air_temp_setpoint=55,  # °F
            has_reheat=True,
            zone_area=400,  # sq ft
            zone_volume=3200,  # cubic ft
            window_area=80,  # sq ft
            window_orientation="south"  # south-facing windows
        )
        vav_boxes.append(vav)
    
    # Create a chilled water AHU
    chw_ahu = AirHandlingUnit(
        name="CHW-AHU",
        cooling_type="chilled_water",
        supply_air_temp_setpoint=55,  # °F
        min_supply_air_temp=52,  # °F
        max_supply_air_temp=65,  # °F
        max_supply_airflow=6000,  # CFM
        vav_boxes=vav_boxes.copy(),  # Copy to avoid shared reference
        enable_supply_temp_reset=True,
        chilled_water_delta_t=12  # 12°F delta-T
    )
    
    # Create a DX AHU
    dx_ahu = AirHandlingUnit(
        name="DX-AHU",
        cooling_type="dx",
        supply_air_temp_setpoint=55,  # °F
        min_supply_air_temp=52,  # °F
        max_supply_air_temp=65,  # °F
        max_supply_airflow=6000,  # CFM
        vav_boxes=vav_boxes.copy(),  # Copy to avoid shared reference
        enable_supply_temp_reset=True,
        compressor_stages=3  # 3-stage compressor
    )
    
    # Simulate over a range of conditions to compare performance
    print("Simulating different cooling types across varying conditions...")
    
    # Temperature range
    outdoor_temps = range(60, 101, 5)  # 60°F to 100°F
    
    # Results storage
    chw_cooling_energy = []
    dx_cooling_energy = []
    chw_flows = []
    dx_stages = []
    
    # Run simulation across temperature range
    for temp in outdoor_temps:
        # Set zone temperatures (hotter when outdoor temp is higher)
        zone_temps = {}
        for i, vav in enumerate(vav_boxes):
            # Different zones have slightly different temps
            zone_temps[f"Zone{i+1}"] = 72 + (temp - 75) * 0.1 * (i+1)
        
        # Update both AHUs
        chw_ahu.update(zone_temps, temp)
        dx_ahu.update(zone_temps, temp)
        
        # Store results
        chw_cooling_energy.append(chw_ahu.cooling_energy / 1000)  # Convert to kBTU/hr
        dx_cooling_energy.append(dx_ahu.cooling_energy / 1000)  # Convert to kBTU/hr
        chw_flows.append(chw_ahu.calculate_chilled_water_flow())  # GPM
        dx_stages.append(dx_ahu.active_compressor_stages)  # Active compressor stages
        
        # Print summary
        print(f"\nOutdoor Temperature: {temp}°F")
        print(f"Chilled Water AHU: Cooling={chw_cooling_energy[-1]:.1f} kBTU/hr, Flow={chw_flows[-1]:.1f} GPM")
        print(f"DX AHU: Cooling={dx_cooling_energy[-1]:.1f} kBTU/hr, Stages={dx_stages[-1]}/{dx_ahu.compressor_stages}")
    
    # Plot results
    plot_results(outdoor_temps, chw_cooling_energy, dx_cooling_energy, chw_flows, dx_stages)

def plot_results(temps, chw_energy, dx_energy, chw_flows, dx_stages):
    """Plot comparison of chilled water and DX performance."""
    fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    
    # Plot 1: Cooling Energy Comparison
    ax1 = axs[0]
    ax1.plot(temps, chw_energy, 'b-', marker='o', label='Chilled Water AHU')
    ax1.plot(temps, dx_energy, 'r-', marker='s', label='DX AHU')
    ax1.set_ylabel('Cooling Energy (kBTU/hr)')
    ax1.set_title('Cooling Energy Comparison')
    ax1.legend()
    ax1.grid(True)
    
    # Add energy difference as percentage
    for i, (chw, dx) in enumerate(zip(chw_energy, dx_energy)):
        if chw > 0 and dx > 0:
            diff_pct = ((dx - chw) / chw) * 100
            temp = temps[i]
            ax1.annotate(f"{diff_pct:.0f}%", 
                         xy=(temp, (chw + dx) / 2), 
                         xytext=(0, 10),
                         textcoords="offset points",
                         ha='center', 
                         fontsize=8)
    
    # Plot 2: Chilled Water Flow Rate
    ax2 = axs[1]
    ax2.plot(temps, chw_flows, 'b-', marker='o')
    ax2.set_ylabel('Chilled Water Flow (GPM)')
    ax2.set_title('Chilled Water Flow Rate')
    ax2.grid(True)
    
    # Add secondary y-axis for cooling energy to show correlation
    ax2_twin = ax2.twinx()
    ax2_twin.plot(temps, chw_energy, 'b--', alpha=0.3)
    ax2_twin.set_ylabel('Cooling Energy (kBTU/hr)', color='b')
    ax2_twin.tick_params(axis='y', labelcolor='b')
    
    # Plot 3: DX Compressor Stages
    ax3 = axs[2]
    
    # Create a bar chart for compressor stages
    bar_width = 2.0
    bars = ax3.bar(temps, dx_stages, width=bar_width, color='r', alpha=0.7)
    
    # Add a line for cooling energy
    ax3_twin = ax3.twinx()
    ax3_twin.plot(temps, dx_energy, 'r--', alpha=0.3)
    ax3_twin.set_ylabel('Cooling Energy (kBTU/hr)', color='r')
    ax3_twin.tick_params(axis='y', labelcolor='r')
    
    ax3.set_ylim(0, 4)  # Assuming max 3 stages + margin
    ax3.set_ylabel('Active Compressor Stages')
    ax3.set_xlabel('Outdoor Temperature (°F)')
    ax3.set_title('DX Compressor Staging')
    ax3.set_xticks(temps)
    ax3.grid(True, axis='y')
    
    # Add efficiency comparison
    fig.suptitle('Cooling System Type Comparison', fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.97])  # Adjust for suptitle
    
    plt.savefig('cooling_types_comparison.png')
    print("\nComparison results saved to cooling_types_comparison.png")

if __name__ == "__main__":
    main()
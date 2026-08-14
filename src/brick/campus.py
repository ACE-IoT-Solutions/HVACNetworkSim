"""Campus and building structure dataclasses for multi-building support.

This module provides data structures for representing campuses with multiple
buildings, each containing their own HVAC equipment topology.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BuildingStructure:
    """Structure representing a single building's HVAC equipment.

    Attributes:
        name: Building identifier/name
        area: Building area in square feet (if available)
        network_number: External BACnet/IP network number (if annotated)
        ip_subnet: Building IP subnet (if annotated by the scenario generator)
        ahus: Dictionary mapping AHU IDs to their configuration
        vavs: Dictionary mapping VAV IDs to their configuration
        zones: Dictionary mapping zone IDs to their configuration
        chillers: Dictionary mapping chiller IDs to their configuration
        boilers: Dictionary mapping boiler IDs to their configuration
        cooling_towers: List of cooling tower IDs
    """

    name: str
    area: Optional[int] = None
    network_number: Optional[int] = None
    ip_subnet: Optional[str] = None
    ahus: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    vavs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    zones: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    chillers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    boilers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cooling_towers: List[str] = field(default_factory=list)

    def get_equipment_summary(self) -> Dict[str, int]:
        """Get a summary count of equipment in this building."""
        return {
            "ahus": len(self.ahus),
            "vavs": len(self.vavs),
            "zones": len(self.zones),
            "chillers": len(self.chillers),
            "boilers": len(self.boilers),
            "cooling_towers": len(self.cooling_towers),
        }

    def has_central_plant(self) -> bool:
        """Check if building has central plant equipment."""
        return bool(self.chillers or self.boilers or self.cooling_towers)


@dataclass
class CampusStructure:
    """Structure representing a campus with multiple buildings.

    Attributes:
        name: Campus identifier/name
        buildings: Dictionary mapping building names to BuildingStructure
    """

    name: str = "Campus"
    buildings: Dict[str, BuildingStructure] = field(default_factory=dict)

    def add_building(self, building: BuildingStructure) -> None:
        """Add a building to the campus."""
        self.buildings[building.name] = building

    def get_building(self, name: str) -> Optional[BuildingStructure]:
        """Get a building by name."""
        return self.buildings.get(name)

    def get_all_equipment_count(self) -> Dict[str, int]:
        """Get total equipment count across all buildings."""
        totals: Dict[str, int] = {
            "buildings": len(self.buildings),
            "ahus": 0,
            "vavs": 0,
            "zones": 0,
            "chillers": 0,
            "boilers": 0,
            "cooling_towers": 0,
        }

        for building in self.buildings.values():
            summary = building.get_equipment_summary()
            for key, value in summary.items():
                totals[key] += value

        return totals

    def is_multi_building(self) -> bool:
        """Check if this campus has multiple buildings."""
        return len(self.buildings) > 1

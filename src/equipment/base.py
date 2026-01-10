"""
Abstract base class for all HVAC equipment.

This module defines the common interface that all equipment types must implement.
It provides a consistent API for:
- Process variable access (get_process_variables, get_process_variables_metadata)
- BACnet integration (optional attachment)
- String representation

Equipment classes should inherit from this base and implement the abstract methods.

Usage:
    from src.equipment.base import Equipment

    class MyEquipment(Equipment):
        def get_process_variables(self) -> Dict[str, Any]:
            return {"name": self.name, "value": self.value}

        @classmethod
        def get_process_variables_metadata(cls) -> Dict[str, Dict[str, Any]]:
            return {"name": {"type": str, "label": "Name"}, ...}
"""

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bacpypes3.app import Application


class EquipmentType(Enum):
    """Enumeration of equipment types for categorization."""

    VAV_BOX = auto()
    AIR_HANDLING_UNIT = auto()
    CHILLER = auto()
    BOILER = auto()
    COOLING_TOWER = auto()
    PUMP = auto()
    BUILDING = auto()
    OTHER = auto()


class Equipment(ABC):
    """
    Abstract base class for all simulated HVAC equipment.

    This class defines the common interface that all equipment must implement.
    It ensures consistent access to process variables and metadata across
    all equipment types.

    Attributes:
        name: Unique identifier for the equipment
        equipment_type: Type of equipment (from EquipmentType enum)

    Abstract Methods:
        get_process_variables: Return current state as dictionary
        get_process_variables_metadata: Return metadata for all variables

    Optional Methods:
        update: Update equipment state (signature varies by equipment type)
    """

    def __init__(self, name: str, equipment_type: EquipmentType = EquipmentType.OTHER) -> None:
        """
        Initialize base equipment.

        Args:
            name: Unique identifier for this equipment
            equipment_type: Type classification for this equipment
        """
        self.name = name
        self.equipment_type = equipment_type
        self._bacnet_app: Optional["Application"] = None

    @abstractmethod
    def get_process_variables(self) -> Dict[str, Any]:
        """
        Return a dictionary of all process variables and their current values.

        This method should return all state variables that would be exposed
        via BACnet or used for monitoring/logging.

        Returns:
            Dictionary mapping variable names to their current values.
            Must include at least 'name' key.

        Example:
            {
                "name": "VAV-101",
                "zone_temp": 72.5,
                "damper_position": 0.65,
                "mode": "cooling"
            }
        """
        pass

    @classmethod
    @abstractmethod
    def get_process_variables_metadata(cls) -> Dict[str, Dict[str, Any]]:
        """
        Return metadata describing all process variables.

        This method provides type information, labels, descriptions, and units
        for each process variable. Used for BACnet object creation and UI display.

        Returns:
            Dictionary mapping variable names to their metadata dictionaries.
            Each metadata dict should contain at least 'type' and 'label'.

        Example:
            {
                "zone_temp": {
                    "type": float,
                    "label": "Zone Temperature",
                    "description": "Current zone air temperature",
                    "unit": "°F"
                },
                "mode": {
                    "type": str,
                    "label": "Operating Mode",
                    "options": ["cooling", "heating", "deadband"]
                }
            }
        """
        pass

    def attach_bacnet_app(self, app: "Application") -> None:
        """
        Attach a BACnet application to this equipment.

        Once attached, the equipment can sync its state to BACnet points.

        Args:
            app: BACpypes3 Application instance
        """
        self._bacnet_app = app

    def detach_bacnet_app(self) -> None:
        """Detach the BACnet application from this equipment."""
        self._bacnet_app = None

    @property
    def has_bacnet(self) -> bool:
        """Check if a BACnet application is attached."""
        return self._bacnet_app is not None

    @property
    def bacnet_app(self) -> Optional["Application"]:
        """Get the attached BACnet application, if any."""
        return self._bacnet_app

    def __str__(self) -> str:
        """Return string representation of equipment."""
        return f"{self.__class__.__name__}({self.name})"

    def __repr__(self) -> str:
        """Return detailed string representation."""
        return f"{self.__class__.__name__}(name={self.name!r}, type={self.equipment_type.name})"


class TerminalUnit(Equipment):
    """
    Abstract base class for terminal units (VAV boxes, fan coil units, etc.).

    Terminal units are the end devices that condition individual zones.
    They typically have:
    - A zone temperature sensor
    - A damper or valve for flow control
    - Optional reheat capability
    """

    def __init__(self, name: str) -> None:
        super().__init__(name, EquipmentType.VAV_BOX)
        self.zone_temp: float = 72.0
        self.zone_temp_setpoint: float = 72.0


class AirHandler(Equipment):
    """
    Abstract base class for air handling equipment (AHUs, RTUs, etc.).

    Air handlers provide conditioned air to one or more zones.
    They typically have:
    - Supply and return fans
    - Heating and cooling coils
    - Dampers for economizer operation
    """

    def __init__(self, name: str) -> None:
        super().__init__(name, EquipmentType.AIR_HANDLING_UNIT)
        self.supply_air_temp: float = 55.0
        self.supply_air_temp_setpoint: float = 55.0


class PlantEquipment(Equipment):
    """
    Abstract base class for central plant equipment (chillers, boilers, towers).

    Plant equipment provides heating or cooling capacity to the building.
    They typically have:
    - Capacity rating
    - Efficiency curves
    - Part load performance characteristics
    """

    def __init__(self, name: str, equipment_type: EquipmentType) -> None:
        super().__init__(name, equipment_type)
        self.capacity: float = 0.0
        self.current_load: float = 0.0

    @property
    def load_ratio(self) -> float:
        """Current load as a fraction of capacity."""
        if self.capacity <= 0:
            return 0.0
        return self.current_load / self.capacity

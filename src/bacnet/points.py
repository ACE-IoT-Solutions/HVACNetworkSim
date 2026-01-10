"""
BACnet point creation and update utilities.

This module provides functions for creating BACnet point objects
and updating their values from equipment process variables.

Usage:
    from src.bacnet.points import create_bacnet_point, update_bacnet_points

    # Create a point
    point = create_bacnet_point(
        point_id=3,
        point_name="zone_temp",
        point_meta={"type": float, "label": "Zone Temp", "unit": "°F"},
        value=72.5
    )

    # Update all points
    count = await update_bacnet_points(app, process_vars)
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Union

from bacpypes3.object import (
    AnalogValueObject,
    BinaryValueObject,
    MultiStateValueObject,
    CharacterStringValueObject,
)

from src.core.constants import BACNET_UPDATE_DELAY_SECONDS

logger = logging.getLogger(__name__)

# Unit conversion mapping from common HVAC units to BACnet units
UNIT_MAPPING: Dict[str, str] = {
    "°F": "degrees-fahrenheit",
    "degF": "degrees-fahrenheit",
    "°C": "degrees-celsius",
    "degC": "degrees-celsius",
    "CFM": "cubic-feet-per-minute",
    "ft³/min": "cubic-feet-per-minute",
    "GPM": "gallons-per-minute",
    "gal/min": "gallons-per-minute",
    "fraction": "percent",
    "%": "percent",
    "sq ft": "square-feet",
    "cu ft": "cubic-feet",
    "kW": "kilowatts",
    "BTU/hr": "btus-per-hour",
    "tons": "tons-refrigeration",
    "psi": "pounds-force-per-square-inch",
    "in-wg": "inches-of-water",
}


def _convert_unit(unit_text: Optional[str]) -> str:
    """Convert HVAC unit string to BACnet engineering units."""
    if not unit_text:
        return "no-units"
    return UNIT_MAPPING.get(unit_text, "no-units")


def create_bacnet_point(
    point_id: int,
    point_name: str,
    point_meta: Dict[str, Any],
    value: Any
) -> Optional[Union[AnalogValueObject, BinaryValueObject, MultiStateValueObject, CharacterStringValueObject]]:
    """
    Create a BACnet point object from process variable metadata.

    Args:
        point_id: BACnet object instance number
        point_name: Name for the object (objectName property)
        point_meta: Metadata dict with 'type', 'label', optional 'unit', 'options'
        value: Current value for the point

    Returns:
        BACnet object instance, or None if type not supported
    """
    point_type = point_meta.get("type")
    label = point_meta.get("label", point_name)

    try:
        if point_type in (float, int):
            units = _convert_unit(point_meta.get("unit"))
            return AnalogValueObject(
                objectIdentifier=f"analog-value,{point_id}",
                objectName=point_name,
                description=label,
                presentValue=float(value),
                units=units
            )

        elif point_type == bool:
            return BinaryValueObject(
                objectIdentifier=f"binary-value,{point_id}",
                objectName=point_name,
                description=label,
                presentValue=bool(value)
            )

        elif point_type == str:
            options = point_meta.get("options")
            if options:
                # Multi-state value for enumerated strings
                try:
                    state_index = options.index(value) + 1  # 1-based
                except ValueError:
                    state_index = 1

                return MultiStateValueObject(
                    objectIdentifier=f"multi-state-value,{point_id}",
                    objectName=point_name,
                    description=label,
                    presentValue=state_index,
                    numberOfStates=len(options),
                    stateText=options
                )
            else:
                # Character string for free-form text
                return CharacterStringValueObject(
                    objectIdentifier=f"character-string-value,{point_id}",
                    objectName=point_name,
                    description=label,
                    presentValue=str(value)
                )

    except Exception as e:
        logger.warning("Failed to create BACnet point %s: %s", point_name, e)

    return None


async def update_bacnet_points(
    app: Any,
    process_vars: Dict[str, Any],
    epsilon: float = 0.001
) -> int:
    """
    Update BACnet points from process variables.

    This function iterates through all objects in the BACnet application
    and updates their present values from the corresponding process variables.

    Args:
        app: BACpypes3 Application instance
        process_vars: Dictionary of process variable names to values
        epsilon: Threshold for float comparison (default 0.001)

    Returns:
        Number of points updated
    """
    update_count = 0

    try:
        for obj in app.objectIdentifier.values():
            try:
                # Skip objects without objectName
                if not hasattr(obj, "objectName"):
                    continue

                point_name: str = obj.objectName

                # Skip if not in process variables
                if point_name not in process_vars:
                    continue

                value = process_vars[point_name]

                # Skip complex types
                if isinstance(value, (dict, list, tuple)) or value is None:
                    continue

                # Get object type
                obj_type = getattr(obj, "objectType", None)

                # Handle different object types
                if obj_type == "multi-state-value":
                    updated = _update_msv(obj, value)
                elif obj_type == "analog-value":
                    updated = _update_av(obj, value, epsilon)
                elif obj_type == "binary-value":
                    updated = _update_bv(obj, value)
                else:
                    updated = _update_fallback(obj, value)

                if updated:
                    update_count += 1

            except Exception as e:
                logger.warning(
                    "Error updating point %s: %s",
                    getattr(obj, 'objectName', 'unknown'), e
                )

        if update_count > 0:
            logger.debug("Updated %d BACnet points", update_count)

    except Exception as e:
        logger.error("Error in BACnet point update: %s", e)

    # Small delay to avoid overwhelming the BACnet stack
    await asyncio.sleep(BACNET_UPDATE_DELAY_SECONDS)

    return update_count


def _update_msv(obj: Any, value: Any) -> bool:
    """Update a multi-state value object."""
    if not hasattr(obj, "stateText"):
        return False

    state_text = obj.stateText
    if value in state_text:
        idx = state_text.index(value) + 1  # 1-based
        if obj.presentValue != idx:
            obj.presentValue = idx
            return True
    return False


def _update_av(obj: Any, value: Any, epsilon: float) -> bool:
    """Update an analog value object."""
    if not isinstance(value, (int, float)):
        return False

    if abs(obj.presentValue - float(value)) > epsilon:
        obj.presentValue = float(value)
        return True
    return False


def _update_bv(obj: Any, value: Any) -> bool:
    """Update a binary value object."""
    if not isinstance(value, bool):
        return False

    if obj.presentValue != bool(value):
        obj.presentValue = bool(value)
        return True
    return False


def _update_fallback(obj: Any, value: Any) -> bool:
    """Fallback update for other object types."""
    try:
        if hasattr(obj, "presentValue") and obj.presentValue != value:
            obj.presentValue = value
            return True
    except Exception as e:
        logger.debug("Could not update %s: %s", getattr(obj, 'objectName', 'unknown'), e)
    return False

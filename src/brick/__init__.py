"""Brick schema parsing module for HVACNetwork.

This module provides functionality to parse Brick schema TTL files
and extract building structure information for simulation.
"""

from src.brick.campus import BuildingStructure, CampusStructure
from src.brick.parser import BrickParser

__all__ = ["BrickParser", "BuildingStructure", "CampusStructure"]

#!/usr/bin/env python3
"""
Simple BACnet device simulator for testing.
"""
import time
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Run a simple simulation loop."""
    logger.info("Starting HVAC Network BACnet Simulator")
    logger.info(f"BACnet IP: {os.getenv('BACNET_IP', '172.25.0.30')}")
    logger.info(f"BACnet Port: {os.getenv('BACNET_PORT', '47808')}")
    
    # Simulate device operation
    while True:
        logger.info("Simulating BACnet devices...")
        # In a real implementation, this would create BACnet devices
        # For now, just keep the container running
        time.sleep(30)


if __name__ == "__main__":
    main()

#!/bin/sh
set -e

# Create BACnet device configuration if not exists
if [ ! -f /app/configs/bacnet_config.ini ]; then
    cat > /app/configs/bacnet_config.ini <<EOF
[BACpypes]
objectName = HVACSimulator
address = ${BACNET_IP:-172.25.0.30}/24:${BACNET_PORT:-47808}
objectIdentifier = 599
maxApduLengthAccepted = 1024
segmentationSupported = segmentedBoth
vendorIdentifier = 15
EOF
fi

# Start the simulation
exec "$@"
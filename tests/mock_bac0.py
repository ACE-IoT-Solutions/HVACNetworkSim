# Mock BAC0 module for testing
class BACnetPoint:
    """Mock BACnet point class."""
    
    def __init__(self, name, objectType, description=None, units=None, stateText=None):
        self.name = name
        self.objectType = objectType
        self.description = description
        self.units = units
        self.stateText = stateText
        self._value = None
    
    @property
    def value(self):
        return self._value
    
    @value.setter
    def value(self, val):
        self._value = val

class BACnetVirtualDevice:
    """Mock BACnet virtual device class."""
    
    def __init__(self, device_id, device_name, objectList, network=None):
        self.device_id = device_id
        self.device_name = device_name
        self.points = {}
        self.network = network
        
        # Create points based on objectList
        for point_config in objectList:
            name = point_config["name"]
            obj_type = point_config["type"]
            description = point_config.get("description")
            units = point_config.get("units")
            state_text = point_config.get("stateText")
            
            point = BACnetPoint(name, obj_type, description, units, state_text)
            self.points[name] = point
    
    def __getitem__(self, point_name):
        """Allow accessing points using device[point_name] syntax."""
        return self.points.get(point_name)

# Mock the create_device function of BAC0
def create_device(device_id, device_name, objectList, network=None):
    return BACnetVirtualDevice(device_id, device_name, objectList, network)

# Create a mock BAC0 module
class MockBAC0:
    device = type('device', (), {'create_device': create_device})

# For use in tests with import monkey patching
BAC0 = MockBAC0()
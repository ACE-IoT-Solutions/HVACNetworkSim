# HVACNetwork Examples

Run the integration harness through `./hvac-sim` from the repository root.
It selects the simple, Brick, or campus topology and starts the supported
simulator. The Python files here illustrate equipment model APIs; they are not
alternate BACnet or Modbus servers.

## Equipment model examples

- `simple_vav.py` demonstrates one VAV and its thermal behavior without networking.
- `complete_building.py` demonstrates coordinated AHU, plant, and zone models
  without networking.
- `bacnet_device_config.py` contains configuration examples; it has no runtime
  entry point.

Run a model example with `uv run python examples/simple_vav.py` or
`uv run python examples/complete_building.py`.

## Campus fixtures

- `multi_building_campus.ttl`: the default two-building campus fixture.
- `multi_building_campus_collisions.ttl`: duplicate BACnet device IDs on
  different networks.
- `large_campus.ttl`: a six-building scale fixture.

Start a fixture with `./hvac-sim --campus examples/multi_building_campus.ttl`.
Use `./hvac-sim --campus --campus-scenario multi-network` for built-in network
scenarios. See the [main README](../README.md) for all supported options.
Add `-e MODBUS_MODE=gateway` to publish each building's meter bank on a
distinct loopback TCP port.

`test_campus.sh` is an end-to-end **test helper**. It generates a campus stack,
builds images, starts containers, and checks their health and BBMD peering.
It is separate from the supported simulator launcher:

```bash
./examples/test_campus.sh --scenario multi-network --teardown
```

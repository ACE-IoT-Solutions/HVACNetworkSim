# Multi-Network Sim — Compose Changes Needed

**Audience:** HVACNetwork team rebuilding the campus simulator images
**Related:** `docs/plans/multi-network-simulation-requirements.md`, `docs/plans/multi-network-bacnet.md`
**Status:** Concrete ask — apply these and we can kick off integration tests on our side.

Thanks for landing the implementation. Here's exactly what we need in the next rebuild / compose update so our multi-network integration tests (`tests/integration/test_multi_network_e2e.py`, coming after Phase 3 on our side) can run.

## 1. Campus compose — add `BACNET_NETWORK_NUMBER` to the existing sims

File: `docker-compose.campus.yml`, services `sim1` and `sim2`.

```yaml
sim1:
  # ... existing config unchanged ...
  environment:
    - SIMULATION_MODE=brick
    - BRICK_TTL_FILE=/app/brick_schemas/multi_building_campus.ttl
    - BUILDING_NAME=Building1
    - BACNET_SUBNET=24
    - CAMPUS_ROUTES=10.2.0.0/24:10.1.0.102
    - BACNET_NETWORK_NUMBER=100   # <-- add this

sim2:
  # ... existing config unchanged ...
  environment:
    - SIMULATION_MODE=brick
    - BRICK_TTL_FILE=/app/brick_schemas/multi_building_campus.ttl
    - BUILDING_NAME=Building2
    - BACNET_SUBNET=24
    - CAMPUS_ROUTES=10.1.0.0/24:10.2.0.102
    - BACNET_NETWORK_NUMBER=200   # <-- add this
```

Why these specific numbers: they're arbitrary but non-zero, distinct, and match what our integration tests expect as defaults. Any non-zero distinct pair would work; these are just what we'll key our tests off.

This change is backward-compatible for any existing test that was relying on the default `network_number=0`. The numbers only become visible in I-Am responses and in the sims' own `network-port` objects — nothing about the `device_id` space changes.

**Nice-to-have same update on the BBMDs:** `bbmd1` advertises itself as network 100's BBMD, `bbmd2` as network 200's. If the BBMD container image honors the same env var, add it there too. If not, don't block on it.

## 2. Collision-scenario brick schema

For the `(network_attachment_id, device_id)` disambiguation test, we need at least one pair of devices that share a `device_id` across the two buildings. Options, in order of preference:

**Option A: new brick schema (cleanest).** Create `examples/multi_building_campus_collisions.ttl` that's structurally identical to `multi_building_campus.ttl` but has one overlapping device_id — e.g., `AHU-100` in Building1 and `VAV-100` in Building2 both assigned `bacnet:deviceId 100`.

**Option B: env var override.** A sim env var like `DEVICE_ID_BASE` that offsets all device IDs within a building. Running sim1 with `DEVICE_ID_BASE=0` and sim2 with `DEVICE_ID_BASE=0` (against the same schema) produces collisions naturally. Running with different bases avoids them. Less code than a whole new schema file.

**Option C: keep existing non-colliding schema.** We can test 90% of the multi-network work without the collision scenario — distinct-device_id observations on two networks are still structurally different observations (different addresses). The collision case is the hardest one to prove correct but we could defer it if the schema change is costly.

Let us know which option is easiest on your side. We can do the brick schema authoring if that helps (we'd PR against `examples/`).

## 3. No changes needed to the existing sim container logic

We're not asking for anything beyond the env var the team just implemented. The simulator should keep doing what it does today:

- respond to WhoIs with I-Am containing the configured `network_number`
- expose its `network-port` object with the configured `networkNumber`
- refuse to answer requests targeted at a different network (scoped WhoIs)

If any of those already behave correctly, don't touch them.

## 4. What we'll do on our side — you don't need to build these

For clarity on ownership:

- **Multi-homed compose variant** (`tests/integration/compose.multihomed.yml`) that attaches our edge to both `building1` and `building2` directly, **without** `campus-router`. Lives in our repo; doesn't touch HVACNetwork's compose.
- **Integration tests** against both the BBMD-routed campus compose (existing) and the multi-homed variant (new).
- **Phase 3 of the edge plan** — entrypoint loading `BacnetNetworkConfig` from KV. That's still in flight on our side; tests wait on it.

## 5. Verification you can do after rebuild (optional)

If you want to confirm the env var landed correctly before we run tests:

```bash
# From inside the campus network, with a BACnet CLI that can talk to sim1:
bacwi 10.1.0.101 47808       # Who-Is -> I-Am; source should show "100:<device_id>"

# Or read the sim's own network-port object directly:
bacrp 10.1.0.101 network-port,1 network-number  # should return 100
```

The I-Am source format `net:mac` in bacpypes3's decoded form is the signal that the network number made it onto the wire.

## 6. Rough order we'll execute on our side

1. You rebuild `hvac-simulator` with the env var support. ✓ (done, per your message)
2. Apply §1 (add `BACNET_NETWORK_NUMBER` to campus compose) — ~5 min change.
3. Either §2 Option A, B, or C — let us know which you want to do.
4. We push Phase 3 of the edge plan (entrypoint multi-network load).
5. We push `compose.multihomed.yml` and `test_multi_network_e2e.py` on our side.
6. We run the tests against your campus sim.

Steps 1–3 on your side can be done in one small PR. Steps 4–5 on our side are independent and already scoped.

## 7. Open questions to confirm

1. **Does the sim image honor `BACNET_NETWORK_NUMBER` right now after the rebuild?** Just a sanity check before we write tests against it.
2. **Does the BBMD image honor it too, or only the simulator?** Affects whether we can set it on `bbmd1`/`bbmd2` for a more realistic campus.
3. **Collision scenario preference — A, B, or C from §2?** Determines whether we pair on a brick schema or you add an env var.
4. **Anything we should know about scoped WhoIs behavior?** If the sim responds to WhoIs regardless of network, our "discovery scoped to one attachment" test would need to filter responses differently.

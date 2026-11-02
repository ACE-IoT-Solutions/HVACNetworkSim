"""Modbus wire-level and simulation metering regression tests."""

import asyncio
import struct

from src.modbus_meter import MeterBank, ModbusMeterServer


class Load:
    def __init__(self, name):
        self.name = name


class Chiller:
    name = "Chiller"

    def calculate_power_consumption(self):
        return 12.0


class Boiler:
    name = "Boiler"

    def calculate_fuel_consumption(self):
        return {"therms_per_hour": 2.5}


def test_meter_accumulates_once_per_simulated_interval():
    bank = MeterBank("Building")
    load = bank.add(Chiller())
    bank.sample(0.25)
    bank.sample(0.25)
    assert load.energy_kwh == 6.0
    # The building rate is summed from equipment meter rates, then integrated once.
    assert bank.building.power_kw == 12.0
    assert bank.building.energy_kwh == 6.0


def test_gas_meter_integrates_therms_without_electrical_demand():
    bank = MeterBank("Building")
    boiler = bank.add(Boiler())
    bank.sample(0.5)
    assert (boiler.gas_therms_per_hour, boiler.gas_therms) == (2.5, 1.25)
    assert (bank.building.gas_therms, bank.building.power_kw) == (1.25, 0.0)


async def read_registers(port, unit, function=3, start=0, count=10):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    pdu = struct.pack(">BHH", function, start, count)
    writer.write(struct.pack(">HHHB", 47, 0, len(pdu) + 1, unit) + pdu)
    await writer.drain()
    try:
        header = await asyncio.wait_for(reader.readexactly(7), 1)
        transaction, protocol, length, response_unit = struct.unpack(">HHHB", header)
        body = await asyncio.wait_for(reader.readexactly(length - 1), 1)
        assert (transaction, protocol, response_unit) == (47, 0, unit)
        return body
    finally:
        writer.close()
        await writer.wait_closed()


async def gateway_case():
    bank = MeterBank("Building")
    equipment = bank.add(Load("Equipment"))
    equipment.power_kw = 42.5
    equipment.energy_kwh = 123.25
    server = ModbusMeterServer(bank, "gateway", "127.0.0.1", 0, 5500)
    await server.start()
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        body = await read_registers(port, equipment.unit_id)
        assert body[:2] == bytes((3, 20))
        assert struct.unpack(">ff", body[2:10]) == (42.5, 123.25)
        building = await read_registers(port, bank.building.unit_id, function=4)
        assert struct.unpack(">f", building[2:6])[0] == 0.0
        assert await read_registers(port, equipment.unit_id, start=9, count=2) == bytes((0x83, 2))
        assert await read_registers(port, equipment.unit_id, function=6) == bytes((0x86, 1))
    finally:
        await server.close()


async def direct_case():
    bank = MeterBank("Building")
    meter = bank.add(Load("Equipment"))
    meter.power_kw = 7.0
    server = ModbusMeterServer(bank, "direct", "127.0.0.1", 0, 0)
    await server.start()
    try:
        port = server.servers[1].sockets[0].getsockname()[1]
        assert struct.unpack(">f", (await read_registers(port, 255))[2:6])[0] == 7.0
    finally:
        await server.close()


def test_gateway_unit_routing_and_read_only_registers():
    asyncio.run(gateway_case())


def test_direct_meter_uses_its_own_tcp_port():
    asyncio.run(direct_case())

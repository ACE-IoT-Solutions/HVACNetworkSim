"""Read-only Modbus TCP energy meters for simulated HVAC equipment.

The gateway endpoint uses the MBAP unit identifier as an RTU slave address.
Direct endpoints give each meter its own TCP port and accept any nonzero unit ID.
All quantities are IEEE-754 float32, high word first, at zero-based holding or
input register offsets: 0 kW, 2 kWh, 4 therms/hour, 6 therms, 8 thermal kW.
"""

import asyncio
import math
import os
import struct
from dataclasses import dataclass

from src.core.constants import BTU_PER_KWH


@dataclass
class EnergyMeter:
    name: str
    unit_id: int
    equipment: object | None = None
    power_kw: float = 0.0
    energy_kwh: float = 0.0
    gas_therms_per_hour: float = 0.0
    gas_therms: float = 0.0
    thermal_kw: float = 0.0

    def sample(self, hours: float) -> None:
        """Sample current equipment rates and integrate one simulation interval."""
        if hours < 0 or not math.isfinite(hours):
            raise ValueError("meter interval must be finite and non-negative")
        item = self.equipment
        power = thermal = gas = 0.0
        if item is not None:
            kinds = {cls.__name__ for cls in type(item).__mro__}
            if "AirHandlingUnit" in kinds:
                power = item.calculate_fan_power()
                if item.cooling_type == "dx":
                    power += max(0.0, item.cooling_energy) / (3.0 * BTU_PER_KWH)
                thermal = (
                    max(0.0, item.cooling_energy) + max(0.0, item.heating_energy)
                ) / BTU_PER_KWH
            elif "VAVBox" in kinds:
                # Terminal heat transfer is already supplied by upstream equipment.
                thermal = item.calculate_energy_usage()["total"] / BTU_PER_KWH
            elif "Chiller" in kinds or "CoolingTower" in kinds:
                power = item.calculate_power_consumption()
            elif "Boiler" in kinds:
                fuel = item.calculate_fuel_consumption()
                power = fuel.get("kilowatt_hours", 0.0)
                gas = fuel.get("therms_per_hour", 0.0)
        self.power_kw = max(0.0, float(power))
        self.gas_therms_per_hour = max(0.0, float(gas))
        self.thermal_kw = max(0.0, float(thermal))
        self.energy_kwh += self.power_kw * hours
        self.gas_therms += self.gas_therms_per_hour * hours

    def registers(self) -> tuple[int, ...]:
        values = (
            self.power_kw,
            self.energy_kwh,
            self.gas_therms_per_hour,
            self.gas_therms,
            self.thermal_kw,
        )
        return struct.unpack(">10H", b"".join(struct.pack(">f", value) for value in values))


class MeterBank:
    """A building meter plus one meter per registered equipment instance."""

    def __init__(self, building_name: str, unit_id_base: int = 1):
        if not 1 <= unit_id_base <= 247:
            raise ValueError("MODBUS_UNIT_ID_BASE must be between 1 and 247")
        self.building = EnergyMeter(building_name, unit_id_base)
        self.meters = [self.building]

    def add(self, equipment: object) -> EnergyMeter:
        unit_id = self.building.unit_id + len(self.meters)
        if unit_id > 247:
            raise ValueError("Modbus RTU gateway supports at most 247 unit IDs")
        meter = EnergyMeter(
            getattr(equipment, "name", type(equipment).__name__), unit_id, equipment
        )
        self.meters.append(meter)
        return meter

    def sample(self, hours: float) -> None:
        for meter in self.meters[1:]:
            meter.sample(hours)
        self.building.power_kw = sum(m.power_kw for m in self.meters[1:])
        self.building.gas_therms_per_hour = sum(m.gas_therms_per_hour for m in self.meters[1:])
        self.building.thermal_kw = sum(
            m.thermal_kw
            for m in self.meters[1:]
            if not any(cls.__name__ == "VAVBox" for cls in type(m.equipment).__mro__)
        )
        self.building.energy_kwh += self.building.power_kw * hours
        self.building.gas_therms += self.building.gas_therms_per_hour * hours


class ModbusMeterServer:
    def __init__(self, bank: MeterBank, mode: str, host: str, port: int, direct_port_base: int):
        if mode not in {"off", "gateway", "direct", "both"}:
            raise ValueError("MODBUS_MODE must be off, gateway, direct, or both")
        self.bank, self.mode, self.host = bank, mode, host
        self.port, self.direct_port_base = port, direct_port_base
        self.servers: list[asyncio.AbstractServer] = []

    async def start(self) -> None:
        try:
            if self.mode in ("gateway", "both"):
                self.servers.append(
                    await asyncio.start_server(
                        lambda r, w: self._serve(r, w, None), self.host, self.port
                    )
                )
            if self.mode in ("direct", "both"):
                for index, meter in enumerate(self.bank.meters):
                    self.servers.append(
                        await asyncio.start_server(
                            lambda r, w, selected=meter: self._serve(r, w, selected),
                            self.host,
                            self.direct_port_base + index if self.direct_port_base else 0,
                        )
                    )
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        for server in self.servers:
            server.close()
        await asyncio.gather(*(server.wait_closed() for server in self.servers))
        self.servers.clear()

    async def _serve(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        selected: EnergyMeter | None,
    ) -> None:
        try:
            while True:
                header = await reader.readexactly(7)
                transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                if protocol != 0 or not 2 <= length <= 254:
                    break
                pdu = await reader.readexactly(length - 1)
                meter = selected or next((m for m in self.bank.meters if m.unit_id == unit), None)
                if meter is None or unit == 0:
                    continue  # A gateway has no slave at this address; broadcasts get no reply.
                function = pdu[0]
                if function not in (3, 4):
                    response = bytes((function | 0x80, 1))
                elif len(pdu) != 5:
                    response = bytes((function | 0x80, 3))
                else:
                    start, count = struct.unpack(">HH", pdu[1:])
                    registers = meter.registers()
                    if not 1 <= count <= 125 or start + count > len(registers):
                        response = bytes((function | 0x80, 2))
                    else:
                        response = bytes((function, count * 2)) + struct.pack(
                            f">{count}H", *registers[start : start + count]
                        )
                writer.write(
                    struct.pack(">HHHB", transaction, 0, len(response) + 1, unit) + response
                )
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()


async def start_meter_server(bank: MeterBank) -> ModbusMeterServer | None:
    """Start opt-in Modbus service without changing existing BACnet deployments."""
    mode = os.getenv("MODBUS_MODE", "off").strip().lower()
    if mode == "off":
        return None
    server = ModbusMeterServer(
        bank,
        mode,
        os.getenv("MODBUS_HOST", "0.0.0.0"),
        int(os.getenv("MODBUS_PORT", "5020")),
        int(os.getenv("MODBUS_DIRECT_PORT_BASE", "5500")),
    )
    await server.start()
    return server

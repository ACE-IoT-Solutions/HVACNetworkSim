"""Router metrics instrumentation for BACnet router devices.

Wraps a bacpypes3 Application (acting as a router) to count packets and
expose the counters as BACnet AnalogValueObjects on the device.

Usage:
    router_app = network_manager.create_ip_to_vlan_router(...)
    metrics = instrument_router(router_app, num_networks=3)
    # In the simulation loop:
    metrics.update_points()
"""

import time
import logging
from typing import Any

from bacpypes3.local.analog import AnalogValueObject

logger = logging.getLogger(__name__)

# Point IDs start high to avoid colliding with network-port objects
_METRICS_BASE_ID = 100


class RouterMetrics:
    """Packet counters and BACnet point management for a router device."""

    def __init__(self, router_app: Any, num_networks: int):
        self._app = router_app
        self._start_time = time.monotonic()

        # Counters
        self.packets_routed = 0
        self.packets_from_ip = 0
        self.packets_to_ip = 0
        self.who_is_requests = 0
        self.i_am_responses = 0
        self.read_property_requests = 0
        self.write_property_requests = 0
        self.cov_notifications = 0
        self.rejected_packets = 0

        # Create BACnet points and add to router
        pid = _METRICS_BASE_ID
        self._points = {}

        point_defs = [
            ("packets_routed", "Packets Routed", "Total NPDUs routed between networks", "count"),
            ("packets_from_ip", "Packets From IP", "NPDUs received from BACnet/IP", "count"),
            ("packets_to_ip", "Packets To IP", "NPDUs sent to BACnet/IP", "count"),
            ("who_is_requests", "Who-Is Requests", "Who-Is requests processed", "count"),
            ("i_am_responses", "I-Am Responses", "I-Am responses sent", "count"),
            (
                "read_property_requests",
                "ReadProperty Requests",
                "ReadProperty requests processed",
                "count",
            ),
            (
                "write_property_requests",
                "WriteProperty Requests",
                "WriteProperty requests processed",
                "count",
            ),
            ("cov_notifications", "COV Notifications", "COV notifications forwarded", "count"),
            ("rejected_packets", "Rejected Packets", "Packets dropped or rejected", "count"),
            ("uptime_seconds", "Uptime", "Router uptime in seconds", "seconds"),
            ("connected_networks", "Connected Networks", "Number of connected networks", "count"),
        ]

        for attr_name, label, description, unit in point_defs:
            bacnet_unit = "no-units" if unit == "count" else "seconds"
            initial = float(num_networks) if attr_name == "connected_networks" else 0.0
            av = AnalogValueObject(
                objectIdentifier=f"analog-value,{pid}",
                objectName=attr_name,
                description=f"{label} — {description}",
                presentValue=initial,
                units=bacnet_unit,
                covIncrement=1.0,
            )
            router_app.add_object(av)
            self._points[attr_name] = av
            pid += 1

    def update_points(self) -> None:
        """Push current counter values into the BACnet point objects."""
        uptime = time.monotonic() - self._start_time
        values = {
            "packets_routed": self.packets_routed,
            "packets_from_ip": self.packets_from_ip,
            "packets_to_ip": self.packets_to_ip,
            "who_is_requests": self.who_is_requests,
            "i_am_responses": self.i_am_responses,
            "read_property_requests": self.read_property_requests,
            "write_property_requests": self.write_property_requests,
            "cov_notifications": self.cov_notifications,
            "rejected_packets": self.rejected_packets,
            "uptime_seconds": uptime,
        }
        for name, value in values.items():
            pt = self._points.get(name)
            if pt is not None:
                pt.presentValue = float(value)


def instrument_router(router_app: Any, num_networks: int) -> RouterMetrics:
    """Wrap a router Application with packet counting and metric points.

    Hooks into:
    - NSAP.process_npdu  — counts every routed NPDU and direction
    - Application.do_*   — counts request types

    Args:
        router_app: bacpypes3 Application acting as the router
        num_networks: number of connected networks (for the static point)

    Returns:
        RouterMetrics instance (also stored as router_app.router_metrics)
    """
    metrics = RouterMetrics(router_app, num_networks)

    # --- Hook NSAP.process_npdu for packet-level counting ---
    nsap = router_app.nsap
    _original_process_npdu = nsap.process_npdu

    async def _counting_process_npdu(adapter, npdu):
        metrics.packets_routed += 1
        if adapter is nsap.local_adapter:
            metrics.packets_from_ip += 1
        else:
            metrics.packets_to_ip += 1
        return await _original_process_npdu(adapter, npdu)

    nsap.process_npdu = _counting_process_npdu

    # --- Hook Application.do_* handlers for request-level counting ---
    _orig_who_is = getattr(router_app, "do_WhoIsRequest", None)
    _orig_read = getattr(router_app, "do_ReadPropertyRequest", None)
    _orig_write = getattr(router_app, "do_WritePropertyRequest", None)
    _orig_iam = getattr(router_app, "i_am", None)
    _orig_ucov = getattr(router_app, "do_UnconfirmedCOVNotificationRequest", None)
    _orig_ccov = getattr(router_app, "do_ConfirmedCOVNotificationRequest", None)

    if _orig_who_is:

        async def _counting_who_is(apdu):
            metrics.who_is_requests += 1
            return await _orig_who_is(apdu)

        router_app.do_WhoIsRequest = _counting_who_is

    if _orig_read:

        async def _counting_read(apdu):
            metrics.read_property_requests += 1
            return await _orig_read(apdu)

        router_app.do_ReadPropertyRequest = _counting_read

    if _orig_write:

        async def _counting_write(apdu):
            metrics.write_property_requests += 1
            return await _orig_write(apdu)

        router_app.do_WritePropertyRequest = _counting_write

    if _orig_iam:

        def _counting_iam(*args, **kwargs):
            metrics.i_am_responses += 1
            return _orig_iam(*args, **kwargs)

        router_app.i_am = _counting_iam

    if _orig_ucov:

        async def _counting_ucov(apdu):
            metrics.cov_notifications += 1
            return await _orig_ucov(apdu)

        router_app.do_UnconfirmedCOVNotificationRequest = _counting_ucov

    if _orig_ccov:

        async def _counting_ccov(apdu):
            metrics.cov_notifications += 1
            return await _orig_ccov(apdu)

        router_app.do_ConfirmedCOVNotificationRequest = _counting_ccov

    router_app.router_metrics = metrics
    logger.info("Router instrumented with %d metric points", len(metrics._points))
    return metrics

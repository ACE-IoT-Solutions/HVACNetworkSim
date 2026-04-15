#!/usr/bin/env python3
"""Add a network route using Linux SIOCADDRT ioctl.

Used in ace-acl-bbmd containers which have Python but not iproute2.
Equivalent to: ip route add <dest>/<mask> via <gateway>

Usage: python3 add_route.py <dest_ip> <netmask> <gateway_ip>
Example: python3 add_route.py 10.2.0.0 255.255.255.0 10.1.0.254
"""

import ctypes
import ctypes.util
import fcntl
import socket
import sys

# Linux SIOCADDRT ioctl number
SIOCADDRT = 0x890B

# Route flags
RTF_UP = 0x0001
RTF_GATEWAY = 0x0002


class sockaddr_in(ctypes.Structure):
    _fields_ = [
        ("sin_family", ctypes.c_ushort),
        ("sin_port", ctypes.c_ushort),
        ("sin_addr", ctypes.c_byte * 4),
        ("sin_zero", ctypes.c_byte * 8),
    ]


class rtentry(ctypes.Structure):
    _fields_ = [
        ("rt_pad1", ctypes.c_ulong),
        ("rt_dst", sockaddr_in),
        ("rt_gateway", sockaddr_in),
        ("rt_genmask", sockaddr_in),
        ("rt_flags", ctypes.c_ushort),
        ("rt_pad2", ctypes.c_short),
        ("rt_pad3", ctypes.c_ulong),
        ("rt_tos", ctypes.c_ubyte),
        ("rt_class", ctypes.c_ubyte),
        ("rt_pad4", ctypes.c_short * 3),
        ("rt_metric", ctypes.c_short),
        ("rt_dev", ctypes.c_char_p),
        ("rt_mtu", ctypes.c_ulong),
        ("rt_window", ctypes.c_ulong),
        ("rt_irtt", ctypes.c_ushort),
    ]


def ip_to_bytes(ip: str):
    return (ctypes.c_byte * 4)(*[int(x) for x in ip.split(".")])


def add_route(dest: str, netmask: str, gateway: str) -> None:
    """Add a network route via SIOCADDRT ioctl."""
    rt = rtentry()

    rt.rt_dst.sin_family = socket.AF_INET
    rt.rt_dst.sin_addr = ip_to_bytes(dest)

    rt.rt_gateway.sin_family = socket.AF_INET
    rt.rt_gateway.sin_addr = ip_to_bytes(gateway)

    rt.rt_genmask.sin_family = socket.AF_INET
    rt.rt_genmask.sin_addr = ip_to_bytes(netmask)

    rt.rt_flags = RTF_UP | RTF_GATEWAY

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
    try:
        fcntl.ioctl(sock.fileno(), SIOCADDRT, rt)
    finally:
        sock.close()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <dest_ip> <netmask> <gateway_ip>", file=sys.stderr)
        sys.exit(1)

    dest, netmask, gateway = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        add_route(dest, netmask, gateway)
        print(f"Route added: {dest}/{netmask} via {gateway}")
    except OSError as e:
        if e.errno == 17:  # EEXIST - route already exists
            print(f"Route already exists: {dest}/{netmask} via {gateway}")
        else:
            print(f"Failed to add route: {e}", file=sys.stderr)
            sys.exit(1)

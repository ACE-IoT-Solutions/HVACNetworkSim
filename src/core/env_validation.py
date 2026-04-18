"""Validation helpers for environment-driven runtime configuration."""

from __future__ import annotations

import ipaddress
from typing import Iterable

ALLOWED_EXTRA_ENV_VARS = frozenset(
    {
        "BACNET_ADDRESS",
        "BACNET_DEVICE_ID",
        "BACNET_IP",
        "BACNET_PORT",
        "BACNET_SUBNET",
    }
)

MANAGED_RUNTIME_ENV_VARS = frozenset(
    {
        "BRICK_TTL_FILE",
        "BUILDING_NAME",
        "CAMPUS_ROUTES",
        "CUSTOM_SCRIPT",
        "DUPLICATE_DEVICE_IDS",
        "DUPLICATE_NETWORK_NUMBERS",
        "DUPLICATE_ROUTERS",
        "INJECT_ERRORS",
        "MULTI_BUILDING_MODE",
        "SIMULATION_MODE",
    }
)

TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


class EnvironmentValidationError(ValueError):
    """Raised when environment-driven configuration is invalid."""


def parse_integer_value(
    value: str | int,
    *,
    variable_name: str,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    """Parse and range-check an integer configuration value."""

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise EnvironmentValidationError(f"{variable_name} must be an integer") from exc

    if min_value is not None and parsed < min_value:
        raise EnvironmentValidationError(f"{variable_name} must be >= {min_value}")
    if max_value is not None and parsed > max_value:
        raise EnvironmentValidationError(f"{variable_name} must be <= {max_value}")
    return parsed


def parse_boolean_value(value: str, *, variable_name: str) -> bool:
    """Parse a boolean-like string."""

    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise EnvironmentValidationError(
        f"{variable_name} must be one of: {', '.join(sorted(TRUE_VALUES | FALSE_VALUES))}"
    )


def validate_ipv4_address(value: str, *, variable_name: str) -> str:
    """Validate an IPv4 address string."""

    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as exc:
        raise EnvironmentValidationError(f"{variable_name} must be a valid IPv4 address") from exc


def parse_cidr_bits(value: str | int, *, variable_name: str = "BACNET_SUBNET") -> int:
    """Parse a CIDR prefix length."""

    return parse_integer_value(value, variable_name=variable_name, min_value=0, max_value=32)


def validate_bacnet_port(value: str | int, *, variable_name: str = "BACNET_PORT") -> int:
    """Parse and validate a UDP port number."""

    return parse_integer_value(value, variable_name=variable_name, min_value=1, max_value=65535)


def validate_bacnet_device_id(value: str | int, *, variable_name: str = "BACNET_DEVICE_ID") -> int:
    """Parse and validate a BACnet device instance number."""

    return parse_integer_value(value, variable_name=variable_name, min_value=0, max_value=4_194_303)


def normalize_bacnet_address(
    *,
    address: str | None = None,
    ip: str | None = None,
    subnet: str | int = 16,
) -> str:
    """Return a validated BACnet address in ``IP/CIDR`` form."""

    if address:
        try:
            interface = ipaddress.IPv4Interface(address)
        except ValueError as exc:
            raise EnvironmentValidationError(
                "BACNET_ADDRESS must be a valid IPv4 interface like 172.26.0.20/16"
            ) from exc
        return f"{interface.ip}/{interface.network.prefixlen}"

    validated_ip = validate_ipv4_address(ip or "0.0.0.0", variable_name="BACNET_IP")
    validated_subnet = parse_cidr_bits(subnet, variable_name="BACNET_SUBNET")
    return f"{validated_ip}/{validated_subnet}"


def parse_extra_env_var(key: str, value: str) -> tuple[str, str]:
    """Validate a user-supplied extra environment variable."""

    normalized_key = key.strip().upper()
    if not normalized_key:
        raise EnvironmentValidationError("Environment variable names must not be empty")

    if normalized_key in MANAGED_RUNTIME_ENV_VARS or normalized_key not in ALLOWED_EXTRA_ENV_VARS:
        allowed = ", ".join(sorted(ALLOWED_EXTRA_ENV_VARS))
        raise EnvironmentValidationError(
            f"{normalized_key} cannot be set with -e; allowed variables: {allowed}"
        )

    normalized_value = value.strip()

    if normalized_key == "BACNET_ADDRESS":
        normalized_value = normalize_bacnet_address(address=normalized_value)
    elif normalized_key == "BACNET_IP":
        normalized_value = validate_ipv4_address(normalized_value, variable_name=normalized_key)
    elif normalized_key == "BACNET_SUBNET":
        normalized_value = str(parse_cidr_bits(normalized_value, variable_name=normalized_key))
    elif normalized_key == "BACNET_PORT":
        normalized_value = str(validate_bacnet_port(normalized_value, variable_name=normalized_key))
    elif normalized_key == "BACNET_DEVICE_ID":
        normalized_value = str(
            validate_bacnet_device_id(normalized_value, variable_name=normalized_key)
        )

    return normalized_key, normalized_value


def redact_env_assignment(assignment: str) -> str:
    """Hide environment variable values in displayed commands."""

    if "=" not in assignment:
        return assignment
    key, _value = assignment.split("=", 1)
    return f"{key}=<redacted>"


def format_container_command(command: Iterable[str]) -> str:
    """Format a container command for display without leaking env values."""

    formatted: list[str] = []
    redact_next = False

    for token in command:
        if redact_next:
            formatted.append(redact_env_assignment(token))
            redact_next = False
            continue

        formatted.append(token)
        if token in {"-e", "--env"}:
            redact_next = True

    return " ".join(formatted)

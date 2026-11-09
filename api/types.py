"""The formats the API accepts: every value from a client is checked by one of these types before it reaches wg."""

import re
from ipaddress import IPv4Address, IPv6Address, ip_interface, ip_network
from typing import Annotated

from pydantic import AfterValidator, Field

# 32 bytes in base64: 43 characters, the last one with its two low bits unused, and "=".
WG_KEY_PATTERN = re.compile(r"^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$")
# wg-quick's rule for interface names.
INTERFACE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_=+.-]{1,15}$")
# As wg parses it: "off" in any case, or a number, in hexadecimal only with a lowercase "0x".
FWMARK_PATTERN = re.compile(r"^((?i:off)|0x[0-9a-fA-F]+|[0-9]+)$")
# host:port, where host is an IPv4 address, a hostname or a bracketed IPv6 address.
ENDPOINT_PATTERN = re.compile(r"^(?:\[(?P<ipv6>[^\[\]]+)\]|(?P<host>[^:\[\]]+)):(?P<port>[0-9]{1,5})$")
HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


def _check_wg_key(value: str) -> str:
    if not WG_KEY_PATTERN.fullmatch(value):
        raise ValueError("Invalid WireGuard key: expected 44 base64 characters, as printed by wg genkey or wg pubkey")
    return value


def _check_interface_name(value: str) -> str:
    if not INTERFACE_NAME_PATTERN.fullmatch(value):
        raise ValueError("Invalid interface name: expected 1 to 15 letters, digits or _=+.-")
    return value


def _check_address(value: str) -> str:
    for item in value.split(","):
        address = item.strip(" ")  # only spaces: a newline would start a new line in the .conf
        try:
            ip_interface(address)
        except ValueError:
            raise ValueError(f"Invalid address: {address}") from None
    return value


def _check_fwmark(value: str) -> str:
    if value.lower() != "off" and (
        not FWMARK_PATTERN.fullmatch(value) or int(value, 16 if value.startswith("0x") else 10) > 0xFFFFFFFF
    ):
        raise ValueError("Invalid fwmark: expected 'off' or a 32-bit number, in decimal or in hexadecimal with '0x'")
    return value


def _check_allowed_ips(value: str) -> str:
    if value:  # an empty string clears the list
        for item in value.split(","):
            cidr = item.strip(" ")
            try:
                ip_network(cidr[1:] if cidr[:1] in ("+", "-") else cidr, strict=False)
            except ValueError:
                raise ValueError(f"Invalid allowed IP: {cidr}") from None
    return value


def _check_endpoint(value: str) -> str:
    if not _is_valid_endpoint(value):
        raise ValueError("Invalid endpoint: expected IPv4:port, [IPv6]:port or hostname:port")
    return value


def _is_valid_endpoint(endpoint: str) -> bool:
    match = ENDPOINT_PATTERN.fullmatch(endpoint)
    if not match or not 1 <= int(match["port"]) <= 65535:
        return False
    if match["ipv6"] is not None:
        try:
            IPv6Address(match["ipv6"])
        except ValueError:
            return False
        return True
    try:
        IPv4Address(match["host"])
    except ValueError:
        return bool(HOSTNAME_PATTERN.fullmatch(match["host"]))
    return True


WireGuardKey = Annotated[str, AfterValidator(_check_wg_key)]
InterfaceName = Annotated[str, AfterValidator(_check_interface_name)]
Address = Annotated[str, AfterValidator(_check_address)]
Fwmark = Annotated[str, AfterValidator(_check_fwmark)]
Port = Annotated[int, Field(ge=0, le=65535)]
AllowedIPs = Annotated[str, AfterValidator(_check_allowed_ips)]
Endpoint = Annotated[str, AfterValidator(_check_endpoint)]
Keepalive = Annotated[int, Field(ge=0, le=65535)]

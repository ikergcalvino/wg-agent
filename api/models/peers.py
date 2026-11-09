import re
from ipaddress import IPv4Address, IPv6Address, ip_network
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from api.models import WireGuardKey

# host:port, where host is an IPv4 address, a hostname or a bracketed IPv6 address.
ENDPOINT_PATTERN = re.compile(r"^(?:\[(?P<ipv6>[^\[\]]+)\]|(?P<host>[^:\[\]]+)):(?P<port>[0-9]{1,5})$")
HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)

PUBLIC_KEY_DESCRIPTION = (
    "A base64 public key calculated by wg pubkey from a private key, and usually transmitted out of band."
)
ALLOWED_IPS_DESCRIPTION = (
    "A comma-separated list of IP (v4 or v6) addresses with CIDR masks from which incoming traffic for this peer "
    "is allowed and to which outgoing traffic for this peer is directed. The catch-all 0.0.0.0/0 may be specified "
    "for matching all IPv4 addresses, and ::/0 may be specified for matching all IPv6 addresses. "
    "Prefix an entry with + or - to add it to or remove it from the current list instead of replacing the list, "
    "or set to an empty string to remove them all."
)
ENDPOINT_DESCRIPTION = (
    "An endpoint IP or hostname, followed by a colon, and then a port number. IPv6 addresses go in brackets. "
    "This endpoint will be updated automatically to the most recent source IP address and port "
    "of correctly authenticated packets from the peer."
)
PERSISTENT_KEEPALIVE_DESCRIPTION = (
    "A seconds interval, between 1 and 65535 inclusive, of how often to send an authenticated empty packet "
    "to the peer for the purpose of keeping a stateful firewall or NAT mapping valid persistently. "
    "If set to 0, this option is disabled. Reported as null when disabled."
)
LATEST_HANDSHAKE_DESCRIPTION = "Unix timestamp of the most recent handshake, or null if there has been none."
TRANSFER_RX_DESCRIPTION = "Number of bytes received from this peer."
TRANSFER_TX_DESCRIPTION = "Number of bytes transmitted to this peer."


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


AllowedIPs = Annotated[str, AfterValidator(_check_allowed_ips)]
Endpoint = Annotated[str, AfterValidator(_check_endpoint)]


class Peer(BaseModel):
    """A peer, as `wg show` reports it. The preshared key is never returned."""

    # Not validated: it comes from wg.
    public_key: str = Field(description=PUBLIC_KEY_DESCRIPTION)
    allowed_ips: str | None = Field(None, description=ALLOWED_IPS_DESCRIPTION)
    endpoint: str | None = Field(None, description=ENDPOINT_DESCRIPTION)
    persistent_keepalive: int | None = Field(None, description=PERSISTENT_KEEPALIVE_DESCRIPTION)
    latest_handshake: int | None = Field(None, description=LATEST_HANDSHAKE_DESCRIPTION)
    transfer_rx: int = Field(description=TRANSFER_RX_DESCRIPTION)
    transfer_tx: int = Field(description=TRANSFER_TX_DESCRIPTION)


class PeerUpdate(BaseModel):
    """Peer settings applied with `wg set`. Omitted fields are left unchanged."""

    model_config = ConfigDict(extra="forbid")

    allowed_ips: AllowedIPs | None = Field(None, description=ALLOWED_IPS_DESCRIPTION)
    endpoint: Endpoint | None = Field(None, description=ENDPOINT_DESCRIPTION)
    # preshared_key: disabled for now, to be revisited. It would go here as a write-only WireGuardKey.
    persistent_keepalive: int | None = Field(None, ge=0, le=65535, description=PERSISTENT_KEEPALIVE_DESCRIPTION)


class PeerCreate(PeerUpdate):
    """A new peer, added with `wg set`. Only public_key is required, as in wg."""

    public_key: WireGuardKey = Field(description=PUBLIC_KEY_DESCRIPTION)

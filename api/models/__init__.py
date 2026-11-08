import re
from typing import Annotated, Any

from pydantic import AfterValidator

# wg-quick's rule for interface names.
IFACE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_=+.-]{1,15}$")
# 32 bytes in base64: 43 characters, the last one with its two low bits unused, and "=".
WG_KEY_PATTERN = re.compile(r"^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$")

# For private and preshared keys: accepted, never returned.
WRITE_ONLY: dict[str, Any] = {"writeOnly": True}


def _check_wg_key(value: str) -> str:
    if not WG_KEY_PATTERN.fullmatch(value):
        raise ValueError("Invalid WireGuard key: expected 44 base64 characters, as printed by wg genkey or wg pubkey")
    return value


WireGuardKey = Annotated[str, AfterValidator(_check_wg_key)]

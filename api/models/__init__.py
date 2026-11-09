import re
from typing import Annotated

from pydantic import AfterValidator

# 32 bytes in base64: 43 characters, the last one with its two low bits unused, and "=".
WG_KEY_PATTERN = re.compile(r"^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$")


def _check_wg_key(value: str) -> str:
    if not WG_KEY_PATTERN.fullmatch(value):
        raise ValueError("Invalid WireGuard key: expected 44 base64 characters, as printed by wg genkey or wg pubkey")
    return value


WireGuardKey = Annotated[str, AfterValidator(_check_wg_key)]

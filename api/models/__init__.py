import re
from typing import Annotated

from pydantic import AfterValidator

IFACE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_=+.-]{1,15}$")
WG_KEY_PATTERN = re.compile(r"^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$")


def _check_wg_key(value: str) -> str:
    if not WG_KEY_PATTERN.fullmatch(value):
        raise ValueError("Invalid WireGuard key format")
    return value


WireGuardKey = Annotated[str, AfterValidator(_check_wg_key)]

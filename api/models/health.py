from typing import Literal

from pydantic import BaseModel, Field

VERSION_DESCRIPTION = "The agent's version, to tell agents apart when several are deployed."
STATUS_DESCRIPTION = "'error' (with 503) when the agent cannot manage WireGuard on this host."
ERRORS_DESCRIPTION = (
    "Why the status is 'error': wg or wg-quick not installed, no CAP_NET_ADMIN, or the WireGuard kernel module not "
    "loaded. Empty when the status is 'ok'."
)


class Health(BaseModel):
    """The agent's version, and whether it can manage WireGuard on this host."""

    version: str = Field(description=VERSION_DESCRIPTION)
    status: Literal["ok", "error"] = Field(description=STATUS_DESCRIPTION)
    errors: list[str] = Field(description=ERRORS_DESCRIPTION)

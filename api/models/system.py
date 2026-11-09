from typing import Literal

from pydantic import BaseModel, Field

STATUS_DESCRIPTION = "'error' (with 503) when wg cannot query the kernel: no WireGuard module, or no CAP_NET_ADMIN."
ERROR_DESCRIPTION = "Why the status is 'error', or null when it is 'ok'."
VERSION_DESCRIPTION = "The agent's version, to tell agents apart when several are deployed."


class Health(BaseModel):
    """Whether the agent can manage WireGuard on this host, and which version it runs."""

    status: Literal["ok", "error"] = Field(description=STATUS_DESCRIPTION)
    error: str | None = Field(None, description=ERROR_DESCRIPTION)
    version: str = Field(description=VERSION_DESCRIPTION)

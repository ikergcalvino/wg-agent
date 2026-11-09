from typing import Literal

from pydantic import BaseModel, Field

NAME_DESCRIPTION = "Application name."
VERSION_DESCRIPTION = "Application version."
STATUS_DESCRIPTION = "'error' (with 503) when wg cannot query the kernel: no WireGuard module, or no CAP_NET_ADMIN."
ERROR_DESCRIPTION = "Why the status is 'error', or null when it is 'ok'."


class Info(BaseModel):
    """The API's name and version."""

    name: str = Field(description=NAME_DESCRIPTION)
    version: str = Field(description=VERSION_DESCRIPTION)


class Health(BaseModel):
    """Whether the API can manage WireGuard on this host."""

    status: Literal["ok", "error"] = Field(description=STATUS_DESCRIPTION)
    error: str | None = Field(None, description=ERROR_DESCRIPTION)

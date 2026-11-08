from typing import Literal

from pydantic import BaseModel, Field

NAME_DESCRIPTION = "Application name."
VERSION_DESCRIPTION = "Application version."
STATUS_DESCRIPTION = "'degraded' (with 503) when any check is not 'ok'."
CHECKS_DESCRIPTION = "wg_access: wg can query the kernel (WireGuard module loaded and CAP_NET_ADMIN)."


class Info(BaseModel):
    """The API's name and version."""

    name: str = Field(description=NAME_DESCRIPTION)
    version: str = Field(description=VERSION_DESCRIPTION)


class Health(BaseModel):
    """Whether the API can manage WireGuard on this host."""

    status: Literal["ok", "degraded"] = Field(description=STATUS_DESCRIPTION)
    checks: dict[str, Literal["ok", "error"]] = Field(description=CHECKS_DESCRIPTION)

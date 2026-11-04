from typing import Literal

from pydantic import BaseModel, Field


class Info(BaseModel):
    name: str = Field(description="Application name.")
    version: str = Field(description="Application version.")


class Health(BaseModel):
    status: Literal["ok", "degraded"] = Field(description="'degraded' (with 503) when any check is not 'ok'.")
    checks: dict[str, Literal["ok", "error"]] = Field(
        description="wg_access: wg can query the kernel (WireGuard module loaded and CAP_NET_ADMIN).",
    )

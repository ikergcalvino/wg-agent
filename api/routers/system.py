from fastapi import APIRouter, Depends, Response

from api import __version__
from api.auth import verify_api_key
from api.models.system import Health, Info
from api.services import wireguard as wg

router = APIRouter(tags=["system"])


@router.get("", dependencies=[Depends(verify_api_key)])
async def info() -> Info:
    return Info(name="wg-agent", version=__version__)


# Public for healthchecks; 503 when degraded, since Docker's HEALTHCHECK only reads the status code.
@router.get("/health", responses={503: {"model": Health}})
async def health(response: Response) -> Health:
    ok = await wg.has_access()
    if not ok:
        response.status_code = 503
    return Health(status="ok" if ok else "degraded", checks={"wg_access": "ok" if ok else "error"})

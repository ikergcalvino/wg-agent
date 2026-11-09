from fastapi import APIRouter, Response

from api import __version__
from api.models.system import Health
from api.services import wireguard as wg

router = APIRouter(tags=["system"])


# Public for healthchecks; 503 on error, since Docker's HEALTHCHECK only reads the status code.
@router.get("/health", responses={503: {"model": Health}})
async def health(response: Response) -> Health:
    error = await wg.access_error()
    if error is not None:
        response.status_code = 503
    return Health(status="ok" if error is None else "error", version=__version__, error=error)

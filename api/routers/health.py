from fastapi import APIRouter, Response

from api import __version__
from api.models.health import Health
from api.services.health import health_errors

router = APIRouter(tags=["health"])


# Public for healthchecks; 503 on error, since Docker's HEALTHCHECK only reads the status code.
@router.get("/health", responses={503: {"model": Health}})
async def health(response: Response) -> Health:
    errors = health_errors()
    if errors:
        response.status_code = 503
    return Health(version=__version__, status="error" if errors else "ok", errors=errors)

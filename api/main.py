import logging

from fastapi import Depends, FastAPI

from api import NAME, __version__
from api.auth import verify_api_key
from api.config import settings
from api.exceptions import register_exception_handlers
from api.routers import health, interfaces, peers

# Docs included, so nothing is served at "/" and a reverse proxy can forward /api/v1/ as is.
API_PREFIX = "/api/v1"

# uvicorn keeps its own log setup; this only shows the agent's logs, at LOG_LEVEL.
logging.basicConfig(format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
logging.getLogger("wg-agent").setLevel(settings.log_level)

app = FastAPI(
    title=NAME,
    description="Agent that exposes a host's WireGuard interfaces and peers through a REST API.",
    version=__version__,
    docs_url=f"{API_PREFIX}/docs",
    redoc_url=f"{API_PREFIX}/redoc",
    openapi_url=f"{API_PREFIX}/openapi.json",
    openapi_tags=[
        {"name": "interfaces", "description": "Manage WireGuard interfaces"},
        {"name": "peers", "description": "Manage peers on WireGuard interfaces"},
        {"name": "health", "description": "Health and version of the agent"},
    ],
)

register_exception_handlers(app)

# The health check is public: monitors and Docker call it without an API key.
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(interfaces.router, prefix=API_PREFIX, dependencies=[Depends(verify_api_key)])
app.include_router(peers.router, prefix=API_PREFIX, dependencies=[Depends(verify_api_key)])

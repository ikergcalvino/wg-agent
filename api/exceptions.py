import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.services.wireguard import (
    InterfaceAlreadyRunning,
    InterfaceNotFound,
    InterfaceNotRunning,
    WireGuardError,
    WireGuardTimeout,
    WireGuardUnavailable,
)

logger = logging.getLogger("wg-agent")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(InterfaceNotFound)
    async def interface_not_found_handler(request: Request, exc: InterfaceNotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InterfaceNotRunning)
    async def interface_not_running_handler(request: Request, exc: InterfaceNotRunning):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InterfaceAlreadyRunning)
    async def interface_already_running_handler(request: Request, exc: InterfaceAlreadyRunning):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(WireGuardError)
    async def wireguard_error_handler(request: Request, exc: WireGuardError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(WireGuardUnavailable)
    async def wireguard_unavailable_handler(request: Request, exc: WireGuardUnavailable):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(WireGuardTimeout)
    async def wireguard_timeout_handler(request: Request, exc: WireGuardTimeout):
        return JSONResponse(status_code=504, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        logger.exception("unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

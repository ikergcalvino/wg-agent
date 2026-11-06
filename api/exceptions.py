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


_STATUS_CODES: dict[type[Exception], int] = {
    InterfaceNotFound: 404,
    InterfaceNotRunning: 409,
    InterfaceAlreadyRunning: 409,
    WireGuardError: 400,
    WireGuardUnavailable: 503,
    WireGuardTimeout: 504,
}


def register_exception_handlers(app: FastAPI) -> None:
    async def service_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=_STATUS_CODES[type(exc)], content={"detail": str(exc)})

    for exc_type in _STATUS_CODES:
        app.add_exception_handler(exc_type, service_error_handler)

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        logger.exception("unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

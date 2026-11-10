import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("wg-agent")


class AgentError(Exception):
    """An error the API answers with its status_code and the message as detail."""

    status_code = 500


class InterfaceNotFound(AgentError):
    """No WireGuard interface is running with this name and it has no config file."""

    status_code = 404

    def __init__(self, name: str) -> None:
        super().__init__(f"Interface '{name}' not found")


class PeerNotFound(AgentError):
    """The interface has no peer with this public key."""

    status_code = 404

    def __init__(self, public_key: str) -> None:
        super().__init__(f"Peer '{public_key}' not found")


class InterfaceNotRunning(AgentError):
    """The interface has a config file but is down."""

    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(f"Interface '{name}' is not running")


class InterfaceRunning(AgentError):
    """The interface is up, and the action needs it down: up, or delete."""

    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(f"Interface '{name}' is running")


class PeerAlreadyExists(AgentError):
    """Add a peer with a public key the interface already has."""

    status_code = 409

    def __init__(self, public_key: str) -> None:
        super().__init__(f"Peer '{public_key}' already exists")


class InterfaceAlreadyExists(AgentError):
    """Create with a name that already has a config file or a running interface."""

    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(f"Interface '{name}' already exists")


class WireGuardError(AgentError):
    """A wg or wg-quick command failed. The message is its error output."""

    status_code = 400


class WireGuardUnavailable(AgentError):
    """wg or wg-quick cannot be used at all: not installed, or no CAP_NET_ADMIN."""

    status_code = 503


class WireGuardTimeout(AgentError):
    """A wg or wg-quick command did not finish in time."""

    status_code = 504


# Starlette calls every handler with (request, exc), whether it uses both or not.
async def _agent_error(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=getattr(exc, "status_code", 500), content={"detail": str(exc)})


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AgentError, _agent_error)
    app.add_exception_handler(Exception, _unhandled_error)

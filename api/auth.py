import hmac
import os
from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader


def _api_key() -> str:
    # Required: the agent controls the host's WireGuard interfaces, so it never runs unauthenticated.
    key = os.environ.get("API_KEY", "")
    if len(key) < 16:
        raise SystemExit("Invalid configuration: API_KEY must be set, with at least 16 characters")
    return key


API_KEY = _api_key()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: Annotated[str | None, Security(api_key_header)]) -> None:
    # Compare bytes: compare_digest rejects str with non-ASCII characters.
    if not key or not hmac.compare_digest(key.encode(), API_KEY.encode()):
        raise HTTPException(status_code=403, detail="Invalid API key")

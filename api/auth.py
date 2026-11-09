import hmac
from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from api.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: Annotated[str | None, Security(api_key_header)]) -> None:
    # Compare bytes: compare_digest rejects str with non-ASCII characters.
    if not key or not hmac.compare_digest(key.encode(), settings.api_key.encode()):
        raise HTTPException(status_code=403, detail="Invalid API key")

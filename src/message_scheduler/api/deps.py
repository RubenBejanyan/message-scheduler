from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from ..config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str | None = Security(_api_key_header)) -> None:
    if not settings.api_key:
        return  # API_KEY not configured — open access (set it in .env to secure)
    if key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key. Pass it as X-API-Key header.",
        )

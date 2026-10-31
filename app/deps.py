from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ApiKey, User
from app.security import decode_access_token, hash_api_key

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_user_jwt(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """JWT only. Used for account management (e.g. creating API keys)."""
    user_id = decode_access_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise _unauthorized("Invalid or missing token")
    return user


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    api_key: str | None = Depends(api_key_header),
    db: Session = Depends(get_db),
) -> User:
    """JWT (dashboard users) or X-API-Key (log agents). Used for log endpoints."""
    if api_key:
        key = db.scalar(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key(api_key), ApiKey.revoked.is_(False))
        )
        user = db.get(User, key.user_id) if key else None
        if user is None:
            raise _unauthorized("Invalid or revoked API key")
        return user
    return get_current_user_jwt(token, db)

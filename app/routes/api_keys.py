from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_jwt
from app.models import ApiKey, User
from app.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.security import generate_api_key

# JWT-only on purpose: a leaked ingestion key must not be able to mint more keys.
router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyCreated, status_code=201)
def create_key(
    payload: ApiKeyCreate,
    user: User = Depends(get_current_user_jwt),
    db: Session = Depends(get_db),
):
    raw, key_hash = generate_api_key()
    key = ApiKey(user_id=user.id, name=payload.name, prefix=raw[:11], key_hash=key_hash)
    db.add(key)
    db.commit()
    db.refresh(key)
    return ApiKeyCreated(**ApiKeyOut.model_validate(key).model_dump(), key=raw)


@router.get("", response_model=list[ApiKeyOut])
def list_keys(user: User = Depends(get_current_user_jwt), db: Session = Depends(get_db)):
    return db.scalars(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.id.desc())
    ).all()


@router.delete("/{key_id}", status_code=204)
def revoke_key(
    key_id: int, user: User = Depends(get_current_user_jwt), db: Session = Depends(get_db)
):
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    key.revoked = True
    db.commit()
    return Response(status_code=204)

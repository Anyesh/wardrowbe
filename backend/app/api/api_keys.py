"""User API key management endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.api_key import ApiKeyCreatedResponse, ApiKeyCreateRequest, ApiKeyResponse
from app.services.api_key_service import ApiKeyService
from app.utils.auth import get_current_user

router = APIRouter(prefix="/auth/api-keys", tags=["Authentication"])


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: ApiKeyCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiKeyCreatedResponse:
    api_key, token = await ApiKeyService(db).create(current_user.id, request)
    metadata = ApiKeyResponse.model_validate(api_key)
    return ApiKeyCreatedResponse(**metadata.model_dump(), token=token)


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ApiKeyResponse]:
    keys = await ApiKeyService(db).list_for_user(current_user.id)
    return [ApiKeyResponse.model_validate(key) for key in keys]


@router.post("/{key_id}/revoke", response_model=ApiKeyResponse)
async def revoke_api_key(
    key_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiKeyResponse:
    api_key = await ApiKeyService(db).revoke(current_user.id, key_id)
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return ApiKeyResponse.model_validate(api_key)

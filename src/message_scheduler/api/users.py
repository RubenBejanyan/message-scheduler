from fastapi import APIRouter, Depends, HTTPException, status

from ..users import (
    block_user,
    get_user,
    grant_admin,
    list_active_users,
    list_blocked_users,
    revoke_admin,
    unblock_user,
)
from .deps import require_api_key
from .schemas import UserOut

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=list[UserOut])
async def list_users() -> list[UserOut]:
    active = await list_active_users()
    blocked = await list_blocked_users()
    return [UserOut.model_validate(u) for u in active + blocked]


@router.get("/{telegram_id}", response_model=UserOut)
async def get_user_endpoint(telegram_id: int) -> UserOut:
    user = await get_user(telegram_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.model_validate(user)


@router.post("/{telegram_id}/block")
async def block_user_endpoint(telegram_id: int) -> dict[str, bool]:
    if not await block_user(telegram_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"ok": True}


@router.post("/{telegram_id}/unblock")
async def unblock_user_endpoint(telegram_id: int) -> dict[str, bool]:
    if not await unblock_user(telegram_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"ok": True}


@router.post("/{telegram_id}/grant-admin")
async def grant_admin_endpoint(telegram_id: int) -> dict[str, bool]:
    if not await grant_admin(telegram_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"ok": True}


@router.post("/{telegram_id}/revoke-admin")
async def revoke_admin_endpoint(telegram_id: int) -> dict[str, bool]:
    if not await revoke_admin(telegram_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"ok": True}

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.auth.base_config import fastapi_users
from models import User
from database import get_async_session
from modules.users.schemas import UserAddNamecheap

router = APIRouter(
    prefix="/users",
    tags=["User"]
)

current_user = fastapi_users.current_user()


@router.get("")
async def get_users(user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Доступ запрещен!"
        }))
    try:
        query = select(User)
        result = await session.execute(query)
        data = []
        users = result.all()
        for item in users:
            item = item[0]
            data.append({
                "id": item.id,
                "email": item.email,
                "username": item.username,
                "registered_at": item.registered_at,
                "is_active": item.is_active,
                "is_superuser": item.is_superuser,
            })

        return {
            "status": "success",
            "data": data,
            "details": None
        }
    except Exception as e:
        print(e)
        raise (HTTPException(status_code=500, detail={
            "status": "error",
            "data": None,
            "details": {"msg": "Список пользователей получен."}
        }))


@router.get("/me")
async def get_me(user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    try:
        query = select(User).where(User.id == user.id)
        result = await session.execute(query)
        data = result.scalar_one_or_none()

        return {
            "status": "success",
            "data": {
                "id": data.id,
                "email": data.email,
                "username": data.username,
                "registered_at": data.registered_at,
                "is_active": data.is_active,
                "is_superuser": data.is_superuser,
                "namecheap_username": data.namecheap_username,
                "namecheap_api": data.namecheap_api,
            },
            "details": {"msg": "Информация о пользователе получена."}
        }
    except Exception as e:
        print(e)
        raise (HTTPException(status_code=500, detail={
            "status": "error",
            "data": None,
            "details": {"msg": "Ошибка сервера."}
        }))


@router.patch("/namecheap")
async def add_namecheap_credentials(info: UserAddNamecheap, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    user.namecheap_username = info.namecheap_username
    user.namecheap_api = info.namecheap_api

    await session.commit()

    return {"status": "success", "data": None, "msg": None}

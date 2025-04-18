from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, File, UploadFile
from fastapi_cache.decorator import cache
from sqlalchemy import insert, select, desc, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_pagination.ext.async_sqlalchemy import paginate
from fastapi_pagination import Params, Page

from modules.auth.base_config import fastapi_users
from models import User, Domain, Cloudflare, CloudflareStatus
from database import get_async_session
from modules.cloudflare.schemas import AddCloudflare, EditCloudflare, ReturnCloudflare
from tools.cloudflare import validate_credentials

router = APIRouter(
    prefix="/cf",
    tags=["CloudFlare"]
)

current_user = fastapi_users.current_user()


@router.get("", response_model=Page[ReturnCloudflare])
@cache(expire=600)
async def get_cf(user: User = Depends(current_user), params: Params = Depends(), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    try:
        query = select(Cloudflare)
        paginated_cfs = await paginate(session, query, params=params)

        return paginated_cfs
    except Exception as e:
        print(e)
        raise (HTTPException(status_code=500, detail={
            "status": "error",
            "data": None,
            "details": None
        }))


@router.post("")
async def add_cf(cf: AddCloudflare, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Cloudflare).where(Cloudflare.email == cf.email)
    result = await session.execute(query)
    cf_current = result.scalar_one_or_none()

    if cf_current is not None:
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Аккаунт Cloudflare уже добавлен в систему."
        }))

    cf_info = cf.dict()

    cf_valid = await validate_credentials(cf.email, cf.api_key)
    if cf_valid:
        cf_info['status'] = CloudflareStatus.ADDED
    else:
        cf_info['status'] = CloudflareStatus.ERROR

    cf_info['owner_id'] = user.id

    stmt = insert(Cloudflare).values(**cf_info)
    await session.execute(stmt)
    await session.commit()

    return {"status": "success", "data": None, "msg": f"Аккаунт Cloudflare {cf_info['email']} добавлен."}


@router.post("/upload")
async def upload_accounts(file: UploadFile = File(...), user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    content = await file.read()
    content = content.decode("utf-8")
    lines = content.splitlines()

    for line in lines:
        email, password, api_key = map(str.strip, line.split("|"))

        query = select(Cloudflare).where(Cloudflare.email == email)
        result = await session.execute(query)
        cf_current = result.scalar_one_or_none()

        if cf_current is not None:
            continue  # Пропустить, если аккаунт уже существует

        cf_valid = await validate_credentials(email, api_key)
        status = CloudflareStatus.ADDED if cf_valid else CloudflareStatus.ERROR

        cf_info = {
            'email': email,
            'password': password,
            'api_key': api_key,
            'status': status,
            'owner_id': user.id
        }

        stmt = insert(Cloudflare).values(**cf_info)
        await session.execute(stmt)

    await session.commit()

    return {"status": "success", "data": None, "msg": f"Акаунты Cloudflare были добавлены из файла {file.filename}."}


@router.patch("")
async def edit_cf(cf: EditCloudflare, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Cloudflare).where(Cloudflare.id == cf.id)
    result = await session.execute(query)
    cf_current = result.scalar_one_or_none()

    if cf_current is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Аккаунт Cloudflare не найден."
        }))

    cf_current.email = cf.email
    cf_current.password = cf.password
    cf_current.api_key = cf.api_key

    cf_valid = await validate_credentials(cf.email, cf.api_key)
    print(cf_valid)

    if cf_valid:
        cf_current.status = CloudflareStatus.ADDED
    else:
        cf_current.status = CloudflareStatus.ERROR

    await session.commit()

    return {"status": "success", "data": None, "msg": f"Аккаунт Cloudflare {cf.email} изменен."}


@router.delete("/{cf_id}")
async def delete_server(cf_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Cloudflare).where(Cloudflare.id == cf_id)
    result = await session.execute(query)
    cf_current = result.scalar_one_or_none()

    if cf_current is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Аккаунт Cloudflare не найден."
        }))

    stmt = delete(Cloudflare).where(Cloudflare.id == cf_id)
    await session.execute(stmt)
    await session.commit()

    return {"status": "success", "data": None, "msg": f"Аккаунт Cloudflare c ID {cf_id} удален."}

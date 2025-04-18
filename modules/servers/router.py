from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi_cache.decorator import cache
from sqlalchemy import insert, select, desc, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_pagination.ext.async_sqlalchemy import paginate
from fastapi_pagination import Params, Page
from tasks import configure_server, delete_domain, restart_apache, create_certs, install_wpcli, install_certbot, \
    generate_private_key, reboot_system, selinux_off, multi_delete_plugin, multi_install_plugin, \
    generate_csv_and_send_email
from modules.auth.base_config import fastapi_users
from models import User, Domain, Server, ServerStatus
from database import get_async_session
from .schemas import ReturnServer, ReturnDomain, AddServer, ServerChangeStatus, UpdateServer
import logging

router = APIRouter(
    prefix="/server",
    tags=["Servers"]
)

current_user = fastapi_users.current_user()


@router.get("", response_model=Page[ReturnServer])
@cache(expire=600)
async def get_servers(
    server_id: Optional[int] = None,
    ip: Optional[str] = None,
    server_name: Optional[str] = None,
    user: User = Depends(current_user), 
    params: Params = Depends(), 
    session: AsyncSession = Depends(get_async_session)
):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    try:
        # Базовый запрос
        query = select(Server)
        
        # Фильтрация по ID сервера, если указан
        if server_id is not None:
            query = query.where(Server.id == server_id)
            
        # Фильтрация по IP-адресу, если указан
        if ip is not None:
            query = query.where(Server.ip.like(f"%{ip}%"))
            
        # Фильтрация по имени сервера, если указано
        if server_name is not None:
            query = query.where(Server.server_name.like(f"%{server_name}%"))
            
        # Сортировка по убыванию ID
        query = query.order_by(desc(Server.id))
        
        # Пагинация результатов
        paginated_servers = await paginate(session, query, params=params)

        return paginated_servers

    except Exception as e:
        print(e)
        raise (HTTPException(status_code=500, detail={
            "status": "error",
            "data": None,
            "details": None
        }))


@router.post("")
async def add_server(
    server: AddServer,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_async_session)
):
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "error",
                "data": None,
                "details": "Your account is not active!"
            }
        )

    # Проверка, существует ли сервер с таким IP
    query = select(Server).where(Server.ip == server.ip)
    result = await session.execute(query)
    server_current = result.scalar_one_or_none()

    if server_current is not None:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "data": None,
                "details": "Сервер уже добавлен в систему."
            }
        )

    # Подготовка данных для вставки
    server_info = server.dict(exclude_unset=True)  # Исключаем неустановленные поля
    server_info['owner_id'] = user.id
    server_info['status'] = ServerStatus.ADDED  # Явно задаём статус

    # Вставка в базу данных
    stmt = insert(Server).values(**server_info)
    await session.execute(stmt)
    await session.commit()

    # Запуск асинхронной задачи
    configure_server.delay(server.ip, server.login, server.password, server.port)

    return {"status": "success", "data": None, "msg": f"Сервер {server.ip} добавлен."}

@router.post("/ssh_key")
async def create_ssh_key(server_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server_current = result.scalar_one_or_none()

    if server_current is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    generate_private_key.delay(server_current.ip, server_current.login, server_current.password, server_current.port)

    return {"status": "success", "data": None, "msg": f"Сервер {server_current.ip} начал выпуск SSH Private Key."}


@router.post("/install_wp_cli/{server_id}")
async def install_wp_cli(server_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    install_wpcli.delay(server.ip, server.login, server.password, server.port)

    return {"status": "success", "data": None, "msg": f"Началась установка WP-CLI на сервер {server.ip}."}


@router.post("/install_certbot/{server_id}")
async def install_certbot_on_server(server_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    install_certbot.delay(server.ip, server.login, server.password, server.port)

    return {"status": "success", "data": None, "msg": f"Началась установка WP-CLI на сервер {server.ip}."}


@router.delete("/{server_id}")
async def delete_server(server_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    query = select(Domain).where(Domain.server_id == server_id)
    result = await session.execute(query)
    domains = result.all()
    if domains:
        domains = domains[0]
        for domain in domains:
            delete_domain.delay(domain.domain, domain.server.ip, domain.server.login, domain.server.password, domain.server.port)

    stmt = delete(Domain).where(Domain.server_id == server_id)
    await session.execute(stmt)

    stmt = delete(Server).where(Server.id == server_id)
    await session.execute(stmt)

    await session.commit()

    return {"status": "success", "data": None, "msg": f"Сервер c ID {server_id} удален."}


@router.put("/{server_id}/sites/plugins")
async def server_install_plugin_for_sites(server_id: int, plugin_name: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    domains = []
    for domain in server.domains:
        domains.append(domain.domain)

    multi_install_plugin.delay(domains, plugin_name, server.ip, server.login, server.password, server.port)

    return {"status": "success", "data": None, "msg": "Установка плагина запущено"}


@router.delete("/{server_id}/sites/plugins")
async def server_delete_plugin_from_sites(server_id: int, plugin_name: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    domains = []
    for domain in server.domains:
        domains.append(domain.domain)

    multi_delete_plugin.delay(domains, plugin_name, server.ip, server.login, server.password, server.port)

    return {"status": "success", "data": None, "msg": "Удаление плагина запущено"}


@router.post("/create_ssl/{server_id}")
async def server_create_ssl_for_domains(server_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    domains = []
    for domain in server.domains:
        domains.append(domain.domain)

    create_certs.delay(domains, server.ip, server.login, server.password, server.port)

    return {"status": "success", "data": None, "msg": None}


@router.post("/restart_apache/{server_id}")
async def server_restart_apache(server_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    restart_apache.delay(server.ip, server.login, server.password, server.port)

    return {"status": "success", "data": None, "msg": None}



@router.get("/{server_id}/domains", response_model=Page[ReturnDomain])
async def get_domains_by_server(
    server_id: int,
    user: User = Depends(current_user),
    params: Params = Depends(),
    session: AsyncSession = Depends(get_async_session)
):
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "error",
                "data": None,
                "details": "Your account is not active!"
            }
        )

    try:
        # Проверка, существует ли сервер и принадлежит ли он пользователю
        query = select(Server).where(Server.id == server_id)
        result = await session.execute(query)
        server = result.scalar_one_or_none()

        if server is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "error",
                    "data": None,
                    "details": "Сервер не найден или не принадлежит вам."
                }
            )

        # Запрос для получения доменов, связанных с сервером
        query = select(Domain).where(Domain.server_id == server_id).order_by(desc(Domain.id))

        # Пагинация
        paginated_domains = await paginate(session, query, params=params)

        # Логирование
        logging.getLogger(__name__).info(f"Fetched domains for server {server_id} for user {user.id}")

        return paginated_domains

    except Exception as e:
        logging.getLogger(__name__).error(f"Error fetching domains for server {server_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "data": None,
                "details": "Internal server error"
            }
        )


@router.patch("/reboot/{server_id}")
async def server_reboot(server_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    reboot_system.delay(server.ip, server.login, server.password, server.port)

    return {"status": "success", "data": None, "msg": None}


@router.patch("/selinux/off/{server_id}")
async def server_off_selinux(server_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Your account is not active!"
        }))

    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    selinux_off.delay(server.ip, server.login, server.password, server.port)

    return {"status": "success", "data": None, "msg": None}


@router.patch("/change_status")
async def change_status_domain(server_info: ServerChangeStatus, session: AsyncSession = Depends(get_async_session)):
    query = select(Server).where(Server.ip == server_info.server_ip)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    server.status = server_info.status
    await session.commit()

    return {"status": "success", "data": None, "msg": None}


@router.patch("/report/domains")
async def get_domains_report(server_ids: List[int], user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    query = select(Domain).where(Domain.server_id.in_(server_ids))
    result = await session.execute(query)
    domains = result.scalars().all()

    # Подготовка данных для передачи в Celery
    domains_data = [{
        'domain': domain.domain,
        'server_ip': domain.server.ip,
        'added_at': domain.added_at.isoformat(),
        'wp_login': domain.wp_login,
        'wp_pass': domain.wp_pass
    } for domain in domains]

    generate_csv_and_send_email.delay(domains_data, user.email)

@router.put("/{server_id}", response_model=ReturnServer)
async def update_server(
    server_id: int, 
    server_data: UpdateServer,
    user: User = Depends(current_user), 
    session: AsyncSession = Depends(get_async_session)
):
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "error",
                "data": None,
                "details": "Your account is not active!"
            }
        )

    # Проверяем, существует ли сервер
    query = select(Server).where(Server.id == server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "data": None,
                "details": "Сервер не найден."
            }
        )

    # Проверяем, не занят ли уже новый IP другим сервером, если IP меняется
    if server_data.ip and server_data.ip != server.ip:
        check_query = select(Server).where(Server.ip == server_data.ip, Server.id != server_id)
        check_result = await session.execute(check_query)
        existing_server = check_result.scalar_one_or_none()
        
        if existing_server:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "error",
                    "data": None,
                    "details": f"Сервер с IP {server_data.ip} уже существует."
                }
            )

    # Подготавливаем данные для обновления
    update_data = server_data.dict(exclude_unset=True)  # Используем только установленные поля
    
    if update_data:
        # Обновляем только указанные поля
        stmt = update(Server).where(Server.id == server_id).values(**update_data)
        await session.execute(stmt)
        await session.commit()
        
        # Получаем обновленные данные сервера
        query = select(Server).where(Server.id == server_id)
        result = await session.execute(query)
        updated_server = result.scalar_one_or_none()
        
        return updated_server
    else:
        return server  # Возвращаем существующий сервер, если нет данных для обновления

@router.get("/{server_id}", response_model=ReturnServer)
async def get_server_by_id(
    server_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_async_session)
):
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "error",
                "data": None,
                "details": "Your account is not active!"
            }
        )

    try:
        # Запрос данных сервера по ID
        query = select(Server).where(Server.id == server_id)
        result = await session.execute(query)
        server = result.scalar_one_or_none()

        if server is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "error",
                    "data": None,
                    "details": "Сервер не найден."
                }
            )

        return server

    except HTTPException:
        raise
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "data": None,
                "details": "Произошла внутренняя ошибка сервера."
            }
        )
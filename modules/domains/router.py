import paramiko
from fastapi import APIRouter, Depends, HTTPException, Header, File, UploadFile, Query
from fastapi_cache.decorator import cache
from sqlalchemy import insert, select, desc, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func
from fastapi_pagination.ext.async_sqlalchemy import paginate
from fastapi_pagination import Params, Page
from modules.auth.base_config import fastapi_users
from models import User, Domain, Server, Cloudflare, WhitePageStatus, WhiteKeywords, Themes
from database import get_async_session
from modules.domains.schemas import DomainCreate, DomainChangeStatus, \
    DomainPostData, DomainAddForm, DomainAddWPAccess, DomainChangeKeyword, ReturnDomain, DomainTransfer
from tasks import delete_domain, install_wordpress, install_plugins, \
    change_theme, create_posts, add_form, configure_http, delete_posts, newadmin_wordpress, transfer_wordpress_site
from tools.certbot import generate_lets_encrypt_cert, configure_ssl_in_apache
from tools.cloudflare import check_ns_records, get_zone_id, delete_all_dns_records, add_a_records, get_ns_records, \
    add_domain_cf, check_zone_status, set_ssl_full, get_ssl_certificate, get_certificate_id, set_ssl_flex
from tools.namecheap import check_domain_in_namecheap, update_ns_records_on_namecheap
from tools.system_func import change_wp_status

router = APIRouter(
    prefix="/domains",
    tags=["Domain"]
)

current_user = fastapi_users.current_user()


@router.get("", response_model=Page[ReturnDomain])
@cache(expire=600)
async def get_domains(
        user: User = Depends(current_user),
        params: Params = Depends(),
        session: AsyncSession = Depends(get_async_session),
        domain_name: str = Query(None, description="Name or partial name of the domain to search")
):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    try:
        query = select(Domain).order_by(desc(Domain.id))

        if domain_name:
            search_pattern = f"%{domain_name}%"
            query = query.where(Domain.domain.ilike(search_pattern))

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
async def add_domain(domain: DomainCreate, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    problems = []

    query = select(Domain).where(Domain.domain == domain.domain)
    result = await session.execute(query)
    domain_current = result.scalar_one_or_none()

    if domain_current is not None:
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Домен уже добавлен в систему."
        }))

    query = select(Server).where(Server.id == domain.server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Указанный сервер не найден."
        }))

    query = (
        select(Cloudflare)
        .outerjoin(Domain)
        .options(joinedload(Cloudflare.domain))
        .where(Domain.id == None)
    )

    result = await session.execute(query)
    cf_current = result.first()

    if cf_current is None:
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Нет доступных аккаунтов Cloudflare."
        }))

    domain_info = domain.dict()
    domain_info['cf_id'] = cf_current[0].id
    domain_info['owner_id'] = user.id
    ns_records = await add_domain_cf(domain_info['domain'], cf_current[0].email, cf_current[0].api_key)
    if ns_records is None:
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Не удалось добавить домен."
        }))

    domain_info['cf_connected'] = False
    domain_info['ns_record_first'] = ns_records[0]
    domain_info['ns_record_second'] = ns_records[1]

    if domain_info['namecheap_integration']:
        if user.namecheap_api is not None:
            update_status = await update_ns_records_on_namecheap(
                domain_info['domain'],
                ns_records[0],
                ns_records[1],
                user.namecheap_username,
                user.namecheap_api
            )
            if not update_status:
                problems.append(f"Автоматическое изменение NS записей для домена {domain_info['domain']} не выполнено из-за ошибки.")
        else:
            problems.append(f"У вас не указаны данные от вашего аккаунта Namecheap.")
    else:
        problems.append(f"Автоматическое изменение NS записей для домена {domain_info['domain']} не выполнено.")

    stmt = insert(Domain).values(**domain_info)
    await session.execute(stmt)
    await session.commit()

    return {
        "status": "success",
        "data": None,
        "details": {
            "msg": f"Домен {domain.domain} добавлен. NS: {ns_records}",
            "problems": problems
        }
    }


@router.post("/upload")
async def upload_accounts(file: UploadFile = File(...), user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    try:
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
            try:
                domain, keyword, server_id, nc_intregration = map(str.strip, line.split("|"))
                server_id = int(server_id)

                query = select(Domain).where(Domain.domain == domain)
                result = await session.execute(query)
                domain_current = result.scalar_one_or_none()

                if domain_current is not None:
                    raise (HTTPException(status_code=400, detail={
                        "status": "error",
                        "data": None,
                        "details": "Домен уже добавлен в систему."
                    }))

                query = select(Server).where(Server.id == server_id)
                result = await session.execute(query)
                server = result.scalar_one_or_none()

                if server is None:
                    raise (HTTPException(status_code=404, detail={
                        "status": "error",
                        "data": None,
                        "details": "Указанный сервер не найден."
                    }))

                query = (
                    select(Cloudflare)
                    .outerjoin(Domain)
                    .options(joinedload(Cloudflare.domain))
                    .where(Domain.id == None)
                )

                result = await session.execute(query)
                cf_current = result.first()

                if cf_current is None:
                    raise (HTTPException(status_code=400, detail={
                        "status": "error",
                        "data": None,
                        "details": "Нет доступных аккаунтов Cloudflare."
                    }))

                domain_info = {
                    'domain': domain,
                    'keyword': keyword,
                    'server_id': server_id,
                    'namecheap_integration': True if nc_intregration == 'y' else False,
                    'cf_connected': False,
                    'cf_id': cf_current[0].id,
                    'owner_id': user.id
                }

                ns_records = await add_domain_cf(domain_info['domain'], cf_current[0].email, cf_current[0].api_key)
                if ns_records is None:
                    raise (HTTPException(status_code=400, detail={
                        "status": "error",
                        "data": None,
                        "details": "Не удалось добавить домен."
                    }))
                domain_info['ns_record_first'] = ns_records[0]
                domain_info['ns_record_second'] = ns_records[1]

                if domain_info['namecheap_integration']:
                    if user.namecheap_api is not None:
                        await update_ns_records_on_namecheap(
                            domain_info['domain'],
                            ns_records[0],
                            ns_records[1],
                            user.namecheap_username,
                            user.namecheap_api
                        )

                stmt = insert(Domain).values(**domain_info)
                await session.execute(stmt)
            except Exception as e:
                print(f"Домен не добавлен")
                print(line)
                print(e)
                continue

        await session.commit()

        return {"status": "success", "data": None, "msg": f"Домены были добавлены из файла {file.filename}."}
    except Exception as e:
        print(e)
        raise (HTTPException(status_code=500, detail={
            "status": "error",
            "data": None,
            "details": "Ошибка сервера!"
        }))


@router.patch("/configure/{domain_id}")
async def config_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    query = select(Server).where(Server.id == domain.server_id)
    result = await session.execute(query)
    server = result.scalar_one_or_none()

    if server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Сервер не найден."
        }))

    if domain.status is WhitePageStatus.CONFIGURE:
        return {"status": "failed", "data": None, "msg": f"С доменом {domain.domain} в данный момент происходят автоматизированные действия."}
    # elif domain.status is WhitePageStatus.DONE:
    #     return {"status": "failed", "data": None, "msg": f"Настройка для домена {domain.domain} не требуется."}
    else:
        install_wordpress.delay(domain.domain, domain.keyword, server.ip, server.login, server.password, server.port)

    return {"status": "success", "data": None, "msg": f"Началась конфигурация домена {domain.domain}."}


@router.post("/check_ns/{domain_id}")
async def check_ns_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    if domain.cf_id is not None and not domain.cf_connected:
        zone_id = await get_zone_id(domain.domain, domain.cloudflare.email, domain.cloudflare.api_key)
        print(zone_id)
        ns_check_result = await check_zone_status(zone_id, domain.cloudflare.email, domain.cloudflare.api_key)
        print(ns_check_result)
        domain.cf_connected = ns_check_result
        await session.commit()

        if ns_check_result:
            await delete_all_dns_records(zone_id, domain.cloudflare.email, domain.cloudflare.api_key)
            await add_a_records(zone_id, domain.server.ip, domain.cloudflare.email, domain.cloudflare.api_key)

    return {"status": "success", "data": None, "msg": f"NS домена {domain.domain} проверены."}


@router.post("/transfer")
async def transfer_domain(transfer_info: DomainTransfer, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == transfer_info.domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    query = select(Server).where(Server.id == transfer_info.new_server_id)
    result = await session.execute(query)
    new_server = result.scalar_one_or_none()

    if new_server is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Конечный сервер не найден."
        }))

    if domain.cf_id is not None and domain.cf_connected:
        zone_id = await get_zone_id(domain.domain, domain.cloudflare.email, domain.cloudflare.api_key)
        await delete_all_dns_records(zone_id, domain.cloudflare.email, domain.cloudflare.api_key)
        await add_a_records(zone_id, new_server.ip, domain.cloudflare.email, domain.cloudflare.api_key)

        change_mode = await set_ssl_flex(zone_id, domain.cloudflare.email, domain.cloudflare.api_key)
        if not change_mode:
            raise (HTTPException(status_code=400, detail={
                "status": "error",
                "data": None,
                "details": "Ошибка смены SSL Mode!"
            }))

        transfer_wordpress_site.delay(
            domain.domain,
            domain.server.ip,
            domain.server.login,
            domain.server.password,
            domain.server.port,
            new_server.ip,
            new_server.login,
            new_server.password,
            new_server.port
        )

    else:
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Cначала нужно дождаться привязки CloudFlare."
        }))

    return {"status": "success", "data": None, "msg": f"NS домена {domain.domain} проверены."}


@router.post("/config_http/{domain_id}")
async def config_http_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    configure_http.delay(domain.domain, domain.server.ip, domain.server.login, domain.server.password, domain.server.port)

    return {"status": "success", "data": None, "msg": f"Конфиг apache создан для {domain.domain}."}


@router.patch("/set_full_ssl_mode/{domain_id}")
async def set_full_ssl_mode(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    zone_id = await get_zone_id(domain.domain, domain.cloudflare.email, domain.cloudflare.api_key)
    change_mode = await set_ssl_full(zone_id, domain.cloudflare.email, domain.cloudflare.api_key)
    if not change_mode:
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Ошибка смены SSL Mode!"
        }))

    return {"status": "success", "data": None, "msg": f"SSL мод изменен для {domain.domain}."}


@router.patch("/set_flex_ssl_mode/{domain_id}")
async def set_flex_ssl_mode(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    zone_id = await get_zone_id(domain.domain, domain.cloudflare.email, domain.cloudflare.api_key)
    change_mode = await set_ssl_flex(zone_id, domain.cloudflare.email, domain.cloudflare.api_key)
    if not change_mode:
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Ошибка смены SSL Mode!"
        }))

    return {"status": "success", "data": None, "msg": f"SSL мод изменен для {domain.domain}."}


@router.patch("/change_status")
async def change_status_domain(domain_info: DomainChangeStatus, session: AsyncSession = Depends(get_async_session)):
    query = select(Domain).where(Domain.domain == domain_info.domain)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    domain.status = domain_info.status

    if domain_info.complete_step is not None:
        if domain_info.complete_step == "plugins_installed":
            domain.plugins_installed = True
        elif domain_info.complete_step == "theme_changed":
            domain.theme_changed = True
        elif domain_info.complete_step == "posts_created":
            domain.posts_created = True
        elif domain_info.complete_step == "form_added":
            domain.form_added = True
        else:
            pass

    await session.commit()

    return {"status": "success", "data": None, "msg": None}


@router.delete("/{domain_id}")
async def remove_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    delete_domain.delay(domain.domain, domain.server.ip, domain.server.login, domain.server.password, domain.server.port)

    stmt = delete(Domain).where(Domain.id == domain_id)
    await session.execute(stmt)
    await session.commit()

    return {"status": "success", "data": None, "msg": f"Домен с ID {domain_id} удален."}


@router.delete("/posts/{domain_id}")
async def remove_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    delete_posts.delay(domain.domain, domain.server.ip, domain.server.login, domain.server.password, domain.server.port)

    return {"status": "success", "data": None, "msg": f"Все посты у домена {domain.domain} будут удалены."}


@router.patch("/clear_all/{domain_id}")
async def clear_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    delete_domain.delay(domain.domain, domain.server.ip, domain.server.login, domain.server.password, domain.server.port)

    domain.wp_pass = None
    domain.wp_login = None
    domain.plugins_installed = False
    domain.posts_created = False
    domain.theme_changed = False
    domain.form_added = False
    await session.commit()

    return {"status": "success", "data": None, "msg": f"Домен с ID {domain_id} очищен."}


@router.put("/create_admin/{domain_id}")
async def new_admin_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    newadmin_wordpress.delay(domain.domain, domain.server.ip, domain.server.login, domain.server.password, domain.server.port)

    return {"status": "success", "data": None, "msg": f"Началось создания нового админа для домена {domain.domain}."}


@router.patch("/keyword")
async def change_keyword_domain(data: DomainChangeKeyword, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == data.domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    if data.keyword is None:
        query = select(WhiteKeywords).order_by(func.random()).limit(1)
        result = await session.execute(query)
        keyword = result.scalar_one_or_none()
        domain.keyword = keyword.name
    else:
        domain.keyword = data.keyword

    await session.commit()

    return {"status": "success", "data": None, "msg": f"Домен с ID {data.domain_id} изменен."}


@router.patch("/wp/add_creds")
async def add_cms_credentials(info: DomainAddWPAccess, session: AsyncSession = Depends(get_async_session)):
    query = select(Domain).where(Domain.domain == info.domain)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    domain.wp_login = info.login
    domain.wp_pass = info.password

    await session.commit()

    return {"status": "success", "data": None, "msg": None}


@router.put("/wp/{domain_id}/plugins")
async def install_plugins_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    if domain.status != "done":
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Сначала выполните конфигурацию домена или дождитесь ее завершения."
        }))

    if domain.plugins_installed:
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Плагины уже установлены."
        }))

    install_plugins.delay(domain.domain, domain.server.ip, domain.server.login, domain.server.password, domain.server.port)

    return {"status": "success", "data": None, "msg": f"Началась установка плагинов для вайта {domain.domain}."}


@router.put("/wp/{domain_id}/theme")
async def change_theme_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    try:
        if not user.is_active:
            raise (HTTPException(status_code=403, detail={
                "status": "error",
                "data": None,
                "details": "Ваш аккаунт не активирован!"
            }))

        query = select(Domain).where(Domain.id == domain_id)
        result = await session.execute(query)
        domain = result.scalar_one_or_none()

        if domain is None:
            raise (HTTPException(status_code=404, detail={
                "status": "error",
                "data": None,
                "details": "Домен не найден."
            }))

        if domain.status != "done":
            raise (HTTPException(status_code=400, detail={
                "status": "error",
                "data": None,
                "details": "Сначала выполните конфигурацию домена или дождитесь ее завершения."
            }))

        query = select(Themes).order_by(func.random()).limit(1)
        result = await session.execute(query)
        theme_slug = result.scalar_one_or_none()
        print(theme_slug)
        print(theme_slug.name)

        change_theme.delay(domain.domain, theme_slug.name, domain.server.ip, domain.server.login, domain.server.password, domain.server.port)
        domain.form_added = False
        await session.commit()

        return {"status": "success", "data": None, "msg": f"Началась установка темы для вайта {domain.domain}."}
    except:
        raise (HTTPException(status_code=500, detail={
            "status": "error",
            "data": None,
            "details": "Ошибка сервера."
        }))


@router.put("/wp/{domain_id}/posts")
async def create_posts_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    if domain.status != "done":
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Сначала выполните конфигурацию домена или дождитесь ее завершения."
        }))

    create_posts.delay(domain.domain, domain.keyword, 5, domain.server.ip, domain.server.login, domain.server.password, domain.server.port)

    return {"status": "success", "data": None, "msg": f"Началась генерация постов для вайта {domain.domain}."}


@router.put("/wp/{domain_id}/form")
async def add_form_domain(domain_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_async_session)):
    if not user.is_active:
        raise (HTTPException(status_code=403, detail={
            "status": "error",
            "data": None,
            "details": "Ваш аккаунт не активирован!"
        }))

    query = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(query)
    domain = result.scalar_one_or_none()

    if domain is None:
        raise (HTTPException(status_code=404, detail={
            "status": "error",
            "data": None,
            "details": "Домен не найден."
        }))

    if domain.status != "done":
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Сначала выполните конфигурацию домена или дождитесь ее завершения."
        }))

    if domain.form_added:
        raise (HTTPException(status_code=400, detail={
            "status": "error",
            "data": None,
            "details": "Форма уже добавлена."
        }))

    add_form.delay(domain.domain, domain.keyword, domain.server.ip, domain.server.login, domain.server.password, domain.server.port)

    return {"status": "success", "data": None, "msg": f"Началась генерация постов для вайта {domain.domain}."}
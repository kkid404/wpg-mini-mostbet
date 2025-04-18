import aioredis
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_pagination import add_pagination
from modules.auth.base_config import auth_backend, auth_backend_bearer, fastapi_users
from modules.auth.schemas import UserCreate, UserRead
from modules.domains.router import router as router_domains
from modules.servers.router import router as router_servers
from modules.cloudflare.router import router as router_cloudflare
from modules.users.router import router as router_users
from modules.system.router import router as router_system


app = FastAPI(
    title="WPG MINI"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://wp-generate.site", "https://wp-generate.site/", "http://localhost:5050", "https://localhost:5050", "162.0.238.102", "162.0.238.102:5050", "*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# Cookie-based аутентификация (для веб-интерфейса)
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth",
    tags=["Auth"],
)

# Bearer token аутентификация (для API)
app.include_router(
    fastapi_users.get_auth_router(auth_backend_bearer),
    prefix="/auth/jwt",
    tags=["Auth"],
)

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["Auth"],
)

add_pagination(app)

app.include_router(router_domains)
app.include_router(router_servers)
app.include_router(router_cloudflare)
app.include_router(router_users)
app.include_router(router_system)


@app.middleware("http")
async def handle_errors(request: Request, call_next):
    response = await call_next(request)

    if request.url.path.startswith("/pages/"):
        if response.status_code == 401:
            return RedirectResponse(url="/pages/login")
        elif response.status_code == 403:
            return RedirectResponse(url="/pages/403")
        elif response.status_code == 404:
            return RedirectResponse(url="/pages/404")
        elif response.status_code == 500:
            return RedirectResponse(url="/pages/500")

    return response


@app.on_event("startup")
async def startup_event():
    redis = aioredis.from_url("redis://localhost", encoding="utf8", decode_responses=True)
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")



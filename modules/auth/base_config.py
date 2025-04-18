from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (AuthenticationBackend,
                                          CookieTransport, JWTStrategy, BearerTransport)

from modules.auth.manager import get_user_manager
from models import User
from tools.config import config_read


config = config_read("config.ini")
cookie_transport = CookieTransport(cookie_name="token_wpg", cookie_max_age=604800)
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=config.get("SYSTEM", "secret"), lifetime_seconds=604800)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

auth_backend_bearer = AuthenticationBackend(
    name="jwt_bearer",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend, auth_backend_bearer],
)

current_user = fastapi_users.current_user()

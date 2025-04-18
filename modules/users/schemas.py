from datetime import datetime

from pydantic import BaseModel


class ChangeRole(BaseModel):
    user_id: int
    role_id: int


class UserAddNamecheap(BaseModel):
    namecheap_username: str
    namecheap_api: str

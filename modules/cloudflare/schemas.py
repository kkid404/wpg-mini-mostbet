from datetime import datetime
from typing import List

from pydantic import BaseModel

from modules.auth.schemas import UserRead


class AddCloudflare(BaseModel):
    email: str
    password: str
    api_key: str


class EditCloudflare(BaseModel):
    id: int
    email: str
    password: str
    api_key: str


class ReturnCloudflare(BaseModel):
    id: int
    email: str
    password: str
    api_key: str
    status: str
    dns_records: str
    owner_id: int
    added_at: datetime

    class Config:
        orm_mode = True

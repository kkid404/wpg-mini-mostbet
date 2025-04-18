from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel

class AddServer(BaseModel):
    ip: str
    login: str
    password: str
    port: int = 22  # Значение по умолчанию
    payment_date: Optional[date] = None  # Новое поле, опциональное
    server_name: Optional[str] = None    # Новое поле, опциональное

class UpdateServer(BaseModel):
    ip: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None
    port: Optional[int] = None
    server_name: Optional[str] = None
    payment_date: Optional[date] = None

class ServerChangeStatus(BaseModel):
    server_ip: str
    status: str

class ReturnServer(BaseModel):
    id: int
    ip: str
    login: str
    password: str
    port: int
    status: str
    owner_id: int
    added_at: datetime
    payment_date: Optional[date] = None
    server_name: Optional[str] = None

    class Config:
        orm_mode = True

class ReturnDomain(BaseModel):
    id: int
    domain: str
    keyword: str
    server_id: int
    cf_id: int
    cf_connected: bool
    ns_record_first: str
    ns_record_second: str
    status: str  # Или WhitePageStatus, если хотите использовать enum
    plugins_installed: bool
    theme_changed: bool
    posts_created: bool
    form_added: bool
    wp_login: Optional[str]
    wp_pass: Optional[str]
    namecheap_integration: Optional[bool]
    owner_id: int
    added_at: datetime

    class Config:
        orm_mode = True
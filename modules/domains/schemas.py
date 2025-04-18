from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from modules.cloudflare.schemas import ReturnCloudflare
from modules.servers.schemas import ReturnServer


class DomainCreate(BaseModel):
    domain: str
    keyword: str
    server_id: int
    namecheap_integration: Optional[bool] = None


class DomainChangeStatus(BaseModel):
    domain: str
    status: str
    complete_step: Optional[str] = None


class DomainPostData(BaseModel):
    keyword: str
    count: int


class DomainAddForm(BaseModel):
    keyword: str


class DomainAddWPAccess(BaseModel):
    domain: str
    login: str
    password: str


class DomainChangeKeyword(BaseModel):
    domain_id: int
    keyword: Optional[str] = None


class DomainTransfer(BaseModel):
    domain_id: int
    new_server_id: int


class ReturnDomain(BaseModel):
    id: int
    domain: str
    keyword: str
    server_id: int
    cf_id: Optional[int]
    cf_connected: bool
    ns_record_first: Optional[str]
    ns_record_second: Optional[str]
    status: str
    plugins_installed: bool
    theme_changed: bool
    posts_created: bool
    form_added: bool
    wp_login: Optional[str]
    wp_pass: Optional[str]
    namecheap_integration: bool
    owner_id: int
    added_at: datetime

    server: ReturnServer
    cloudflare: ReturnCloudflare

    class Config:
        orm_mode = True
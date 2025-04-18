import enum
from datetime import datetime

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTable
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Date, Boolean, TIMESTAMP, Index, JSON
from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.orm import relationship


Base = declarative_base()


class CloudflareStatus(str, enum.Enum):
    ADDED = "added"
    ERROR = "error"


class CloudflareDNSRecords(str, enum.Enum):
    NONE = "none"
    ADDED = "added"
    ERROR = "error"


class WhitePageStatus(str, enum.Enum):
    DONE = "done"
    ADDED = "added"
    ERROR = "error"
    CONFIGURE = "configure"


class ServerStatus(str, enum.Enum):
    ADDED = "added"
    CONFIGURE = "configure"
    ERROR = "error"


class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = "user"
    
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)
    username = Column(String, nullable=False)
    registered_at = Column(TIMESTAMP, default=datetime.utcnow)
    hashed_password: str = Column(String(length=1024), nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    is_superuser: bool = Column(Boolean, default=False, nullable=False)
    is_verified: bool = Column(Boolean, default=True, nullable=False)

    namecheap_username = Column(String, nullable=True)
    namecheap_api = Column(String, nullable=True)

    domains = relationship("Domain", back_populates='user', lazy="selectin")
    servers = relationship("Server", back_populates='user', lazy="selectin")
    cf_accounts = relationship("Cloudflare", back_populates='user', lazy="selectin")



class Server(Base):
    __tablename__ = "server"
    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, nullable=False)
    login = Column(String, nullable=False)
    password = Column(String, nullable=False)
    port = Column(Integer)
    status = Column(Enum(ServerStatus))
    owner_id = Column(Integer, ForeignKey("user.id"))
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    payment_date = Column(Date, nullable=True)  # Новое поле
    server_name = Column(String, nullable=True)  # Новое поле

    domains = relationship("Domain", back_populates="server", lazy="selectin")
    user = relationship("User", back_populates="servers", lazy="selectin")


class Cloudflare(Base):
    __tablename__ = "cloudflare"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False)
    password = Column(String, nullable=False)
    api_key = Column(String, nullable=False)
    status = Column(Enum(CloudflareStatus), default=CloudflareStatus.ADDED)
    dns_records = Column(Enum(CloudflareDNSRecords), default=CloudflareDNSRecords.NONE)
    owner_id = Column(Integer, ForeignKey("user.id"))
    added_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow())

    domain = relationship("Domain", back_populates="cloudflare", lazy="selectin")
    user = relationship("User", back_populates="cf_accounts", lazy="selectin")


class Domain(Base):
    __tablename__ = "domain"
    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, nullable=False)
    keyword = Column(String, nullable=False)
    server_id = Column(Integer, ForeignKey(Server.id), nullable=False)
    cf_id = Column(Integer, ForeignKey(Cloudflare.id), nullable=False)
    cf_connected = Column(Boolean, nullable=False, default=False)
    ns_record_first = Column(String, nullable=False)
    ns_record_second = Column(String, nullable=False)
    status = Column(Enum(WhitePageStatus), default=WhitePageStatus.ADDED)
    plugins_installed = Column(Boolean, nullable=False, default=False)
    theme_changed = Column(Boolean, nullable=False, default=False)
    posts_created = Column(Boolean, nullable=False, default=False)
    form_added = Column(Boolean, nullable=False, default=False)
    wp_login = Column(String, nullable=True)
    wp_pass = Column(String, nullable=True)
    namecheap_integration = Column(Boolean, nullable=True, default=False)
    # menu_created = Column(Boolean, nullable=False, default=False)
    owner_id = Column(Integer, ForeignKey("user.id"))
    added_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow())

    server = relationship("Server", back_populates="domains", lazy="selectin")
    cloudflare = relationship("Cloudflare", back_populates="domain", lazy="selectin")
    user = relationship("User", back_populates="domains", lazy="selectin")


class WhiteKeywords(Base):
    __tablename__ = "white_keywords"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class BlackKeywords(Base):
    __tablename__ = "black_keywords"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class Themes(Base):
    __tablename__ = "themes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class BlockedThemes(Base):
    __tablename__ = "blocked_themes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


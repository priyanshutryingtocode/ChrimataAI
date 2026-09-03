from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal

from sqlalchemy import String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.core.config import DATA_DIR, settings

DATABASE_FILENAME = "controller.db"
DEFAULT_DATABASE_URL = f"sqlite:///{(DATA_DIR / DATABASE_FILENAME).as_posix()}"

DATA_DIR.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


class MoneyType(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect) -> str | None:
        if value is None:
            return None
        return format(value.quantize(Decimal("0.01")), "f")

    def process_result_value(self, value: str | None, dialect) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)


def _resolve_url() -> str:
    url = settings.database_url.strip()
    if not url:
        return DEFAULT_DATABASE_URL
    if url.startswith("sqlite:///./") or url == "sqlite://":
        return DEFAULT_DATABASE_URL
    return url


engine = create_engine(_resolve_url(), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import batch as batch_models

    Base.metadata.create_all(bind=engine)

from collections.abc import Generator
import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_database_url
from app.database.models import Base


logger = logging.getLogger(__name__)
database_url = get_database_url()

connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


if database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


def init_db() -> None:
    if database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
        return

    logger.info("Banco nao-SQLite detectado; execute migrations Alembic antes de iniciar o bot.")


def get_db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from collections.abc import Generator
import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_database_url


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
        logger.info("Usando SQLite local; executando migrations Alembic.")
        _run_alembic_upgrade()
        return

    logger.info("Banco PostgreSQL detectado; executando migrations Alembic.")
    _run_alembic_upgrade()


def get_db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_alembic_upgrade() -> None:
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError as exc:
        raise RuntimeError("Alembic nao esta instalado. Rode `pip install -r requirements.txt`.") from exc

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

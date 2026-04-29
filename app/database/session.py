from collections.abc import Generator
import logging

from sqlalchemy import create_engine, event, inspect, text
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
        logger.info("Usando SQLite local; criando tabelas automaticamente se necessario.")
        Base.metadata.create_all(bind=engine)
        _ensure_sqlite_schema()
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


def _ensure_sqlite_schema() -> None:
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "receive_updates_notifications" not in user_columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN receive_updates_notifications BOOLEAN NOT NULL DEFAULT 1")
                )

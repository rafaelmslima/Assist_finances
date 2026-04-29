from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database.models import Base


settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


def init_db() -> None:
    if settings.database_url.startswith("sqlite"):
        _prepare_sqlite_user_migration()
    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        _backfill_sqlite_user_ids()


def get_db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _prepare_sqlite_user_migration() -> None:
    with engine.begin() as connection:
        tables = _sqlite_tables(connection)
        if "users" in tables:
            user_columns = _sqlite_columns(connection, "users")
            if "id" not in user_columns:
                connection.execute(text("ALTER TABLE users RENAME TO users_legacy"))

        for table_name in ("expenses", "incomes", "budgets", "fixed_expenses", "daily_notifications"):
            if table_name not in tables:
                continue
            columns = _sqlite_columns(connection, table_name)
            if "user_id" not in columns:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN user_id INTEGER"))


def _backfill_sqlite_user_ids() -> None:
    with engine.begin() as connection:
        tables = _sqlite_tables(connection)
        if "users_legacy" in tables:
            connection.execute(
                text(
                    """
                    INSERT OR IGNORE INTO users (
                        telegram_user_id,
                        telegram_chat_id,
                        first_name,
                        username,
                        is_active,
                        created_at,
                        updated_at
                    )
                    SELECT
                        telegram_user_id,
                        telegram_user_id,
                        NULL,
                        NULL,
                        1,
                        COALESCE(created_at, CURRENT_TIMESTAMP),
                        CURRENT_TIMESTAMP
                    FROM users_legacy
                    """
                )
            )

        for table_name in ("expenses", "incomes", "budgets", "fixed_expenses", "daily_notifications"):
            if table_name not in tables:
                continue
            columns = _sqlite_columns(connection, table_name)
            if "telegram_user_id" not in columns or "user_id" not in columns:
                continue

            connection.execute(
                text(
                    f"""
                    INSERT OR IGNORE INTO users (
                        telegram_user_id,
                        telegram_chat_id,
                        first_name,
                        username,
                        is_active,
                        created_at,
                        updated_at
                    )
                    SELECT DISTINCT
                        telegram_user_id,
                        telegram_user_id,
                        NULL,
                        NULL,
                        1,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    FROM {table_name}
                    WHERE telegram_user_id IS NOT NULL
                    """
                )
            )
            connection.execute(
                text(
                    f"""
                    UPDATE {table_name}
                    SET user_id = (
                        SELECT users.id
                        FROM users
                        WHERE users.telegram_user_id = {table_name}.telegram_user_id
                    )
                    WHERE user_id IS NULL
                    AND telegram_user_id IS NOT NULL
                    """
                )
            )


def _sqlite_tables(connection) -> set[str]:
    rows = connection.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'table'")
    ).fetchall()
    return {str(row[0]) for row in rows}


def _sqlite_columns(connection, table_name: str) -> set[str]:
    rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {str(row[1]) for row in rows}

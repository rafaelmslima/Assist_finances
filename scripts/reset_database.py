import argparse
from pathlib import Path

from sqlalchemy import create_engine, text

from app.config import get_database_url
from app.database.models import Base
from app.database.session import init_db


CONFIRMATION = "RESET_ALL_DATA"
SCHEMA_VERSION = "202604300001"


def main() -> None:
    parser = argparse.ArgumentParser(description="Apaga os dados do banco e recria o schema do Finance Bot.")
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"Obrigatorio para evitar acidentes. Use: {CONFIRMATION}",
    )
    parser.add_argument(
        "--drop-postgres-schema",
        action="store_true",
        help="No PostgreSQL, apaga e recria o schema public inteiro. Use apenas em banco dedicado ao bot.",
    )
    args = parser.parse_args()

    if args.confirm != CONFIRMATION:
        raise SystemExit(f"Confirmacao invalida. Use exatamente: --confirm {CONFIRMATION}")

    database_url = get_database_url()
    if database_url.startswith("sqlite"):
        _reset_sqlite(database_url)
    elif database_url.startswith("postgresql"):
        _reset_postgresql(database_url, args.drop_postgres_schema)
    else:
        raise SystemExit(f"Banco nao suportado para reset automatico: {database_url}")

    try:
        init_db()
    except RuntimeError as exc:
        if "Alembic nao esta instalado" not in str(exc):
            raise
        _create_schema_without_alembic(database_url)
    print("Banco resetado e migrations aplicadas com sucesso.")


def _reset_sqlite(database_url: str) -> None:
    if database_url in {"sqlite:///:memory:", "sqlite+pysqlite:///:memory:"}:
        return
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise SystemExit(f"URL SQLite inesperada: {database_url}")
    db_path = Path(database_url.removeprefix(prefix)).resolve()
    if db_path.exists():
        db_path.unlink()
        print(f"Arquivo SQLite removido: {db_path}")


def _reset_postgresql(database_url: str, drop_schema: bool) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            if drop_schema:
                connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
                connection.execute(text("CREATE SCHEMA public"))
                connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
                print("Schema public do PostgreSQL recriado.")
                return

            Base.metadata.drop_all(bind=connection)
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            print("Tabelas do Finance Bot removidas do PostgreSQL.")
    finally:
        engine.dispose()


def _create_schema_without_alembic(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(text("DELETE FROM alembic_version"))
            connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"), {"version_num": SCHEMA_VERSION})
        print("Alembic indisponivel; schema criado via SQLAlchemy metadata.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

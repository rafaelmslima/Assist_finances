import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    database_url: str = "sqlite:///./finance_bot.db"
    timezone: str = "America/Sao_Paulo"
    allowed_telegram_ids: frozenset[int] = frozenset()


def get_settings() -> Settings:
    load_dotenv()
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_bot_token:
        raise RuntimeError("Configure TELEGRAM_BOT_TOKEN no arquivo .env.")

    return Settings(
        telegram_bot_token=telegram_bot_token,
        database_url=get_database_url(),
        timezone=os.getenv("TIMEZONE", "America/Sao_Paulo"),
        allowed_telegram_ids=_parse_allowed_telegram_ids(os.getenv("ALLOWED_TELEGRAM_IDS")),
    )


def get_database_url() -> str:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return "sqlite:///./finance_bot.db"
    return _normalize_database_url(database_url)


def _normalize_database_url(database_url: str) -> str:
    database_url = database_url.strip()
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _parse_allowed_telegram_ids(raw_value: str | None) -> frozenset[int]:
    if not raw_value:
        return frozenset()

    allowed_ids = set()
    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        allowed_ids.add(int(item))
    return frozenset(allowed_ids)

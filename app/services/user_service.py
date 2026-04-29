from dataclasses import dataclass

from app.config import get_settings
from app.database.models import User
from app.database.repository import UserRepository


@dataclass(frozen=True)
class TelegramUserData:
    telegram_user_id: int
    telegram_chat_id: int
    first_name: str | None
    username: str | None


class UnauthorizedUserError(PermissionError):
    pass


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def is_allowed(self, telegram_user_id: int) -> bool:
        allowed_ids = get_settings().allowed_telegram_ids
        return not allowed_ids or telegram_user_id in allowed_ids

    def register_or_update_from_telegram(self, data: TelegramUserData) -> User:
        if not self.is_allowed(data.telegram_user_id):
            raise UnauthorizedUserError("Usuario nao autorizado a usar este bot.")

        return self.repository.upsert_from_telegram(
            telegram_user_id=data.telegram_user_id,
            telegram_chat_id=data.telegram_chat_id,
            first_name=data.first_name,
            username=data.username,
        )

    def get_registered_user(self, telegram_user_id: int) -> User | None:
        if not self.is_allowed(telegram_user_id):
            raise UnauthorizedUserError("Usuario nao autorizado a usar este bot.")
        return self.repository.get_by_telegram_user_id(telegram_user_id)

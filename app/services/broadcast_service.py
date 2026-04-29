import logging
from dataclasses import dataclass

from app.database.repository import UpdateBroadcastRepository, UserRepository


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BroadcastResult:
    total_users: int
    sent_count: int
    failed_count: int


class BroadcastService:
    def __init__(
        self,
        user_repository: UserRepository,
        broadcast_repository: UpdateBroadcastRepository,
    ):
        self.user_repository = user_repository
        self.broadcast_repository = broadcast_repository

    async def send_update_broadcast(self, bot, admin_user_id: int, message: str) -> BroadcastResult:
        recipients = self.user_repository.list_active_update_recipients()
        sent_count = 0
        failed_count = 0

        for user in recipients:
            try:
                await bot.send_message(chat_id=user.telegram_chat_id, text=message)
                sent_count += 1
            except Exception as exc:
                failed_count += 1
                logger.warning(
                    "Falha ao enviar broadcast de update para user_id=%s error_type=%s",
                    user.id,
                    exc.__class__.__name__,
                )

        result = BroadcastResult(
            total_users=len(recipients),
            sent_count=sent_count,
            failed_count=failed_count,
        )
        self.broadcast_repository.create(
            admin_user_id=admin_user_id,
            message=message,
            total_users=result.total_users,
            sent_count=result.sent_count,
            failed_count=result.failed_count,
        )
        return result

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from app.bot.commands import format_forecast
from app.config import get_settings
from app.database.repository import (
    BudgetRepository,
    DailyNotificationRepository,
    ExpenseRepository,
    FixedExpenseRepository,
    IncomeRepository,
    UserRepository,
)
from app.database.session import SessionLocal
from app.services.analytics_service import AnalyticsService


logger = logging.getLogger(__name__)


async def send_daily_forecasts(application: Application) -> None:
    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.timezone)).date()

    with SessionLocal() as db:
        user_repository = UserRepository(db)
        notification_repository = DailyNotificationRepository(db)
        users = user_repository.list_active_users()

    for user in users:
        try:
            with SessionLocal() as db:
                notification_repository = DailyNotificationRepository(db)
                if notification_repository.was_sent(user.id, today):
                    continue

                analytics = AnalyticsService(
                    ExpenseRepository(db),
                    IncomeRepository(db),
                    BudgetRepository(db),
                    FixedExpenseRepository(db),
                )
                forecast = analytics.get_forecast(user.id, today)
                message = format_forecast(forecast, daily=True)

            await application.bot.send_message(chat_id=user.telegram_chat_id, text=message)

            with SessionLocal() as db:
                DailyNotificationRepository(db).mark_sent(user.id, today)
        except Exception:
            logger.exception("Falha ao enviar previsao diaria para user_id=%s", user.id)


def start_daily_scheduler(application: Application) -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.timezone))
    scheduler.add_job(
        send_daily_forecasts,
        trigger="cron",
        hour=8,
        minute=0,
        args=[application],
        id="daily_financial_forecast",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    return scheduler

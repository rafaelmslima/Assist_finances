import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from app.bot.commands import format_forecast, format_salary_auto_reloaded
from app.config import get_settings
from app.database.repository import (
    BudgetRepository,
    DailyNotificationRepository,
    ExpenseRepository,
    FixedExpenseRepository,
    IncomeRepository,
    SalaryConfigRepository,
    UserRepository,
)
from app.database.session import SessionLocal
from app.database.models import User
from app.services.analytics_service import AnalyticsService
from app.services.salary_service import SalaryService


logger = logging.getLogger(__name__)
DAILY_FORECAST_CONCURRENCY = 5


async def send_daily_forecasts(application: Application) -> None:
    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.timezone)).date()

    with SessionLocal() as db:
        user_repository = UserRepository(db)
        users = user_repository.list_active_users()

    semaphore = asyncio.Semaphore(DAILY_FORECAST_CONCURRENCY)
    await _auto_reload_due_salaries(application, users, today, semaphore)
    await asyncio.gather(
        *[
            _send_daily_forecast_to_user(application, user, today, semaphore)
            for user in users
        ]
    )


async def _send_daily_forecast_to_user(
    application: Application,
    user: User,
    today: date,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        try:
            with SessionLocal() as db:
                notification_repository = DailyNotificationRepository(db)
                if not notification_repository.try_mark_sent(user.id, today):
                    return

                analytics = AnalyticsService(
                    ExpenseRepository(db),
                    IncomeRepository(db),
                    BudgetRepository(db),
                    FixedExpenseRepository(db),
                    SalaryConfigRepository(db),
                )
                forecast = analytics.get_forecast(user.id, today)
                message = format_forecast(forecast, daily=True)

            await application.bot.send_message(chat_id=user.telegram_chat_id, text=message)
        except Exception:
            with SessionLocal() as db:
                DailyNotificationRepository(db).clear_sent_marker(user.id, today)
            logger.exception("Falha ao enviar previsao diaria para user_id=%s", user.id)


async def _auto_reload_due_salaries(
    application: Application,
    users: list[User],
    today: date,
    semaphore: asyncio.Semaphore,
) -> None:
    await asyncio.gather(
        *[
            _auto_reload_salary_for_user(application, user, today, semaphore)
            for user in users
        ]
    )


async def _auto_reload_salary_for_user(
    application: Application,
    user: User,
    today: date,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        try:
            with SessionLocal() as db:
                income = SalaryService(
                    SalaryConfigRepository(db),
                    IncomeRepository(db),
                ).register_auto_salary_if_due(user.id, today)
                if not income:
                    return
                message = format_salary_auto_reloaded(income.amount)

            await application.bot.send_message(chat_id=user.telegram_chat_id, text=message)
        except Exception:
            logger.exception("Falha ao recarregar salario automatico para user_id=%s", user.id)


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

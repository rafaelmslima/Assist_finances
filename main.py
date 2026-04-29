import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.bot.handlers import (
    add_expense,
    add_fixed_expense,
    add_income,
    balance,
    category_chart,
    compare_months,
    day_summary,
    delete_expense,
    delete_fixed_expense,
    edit_expense,
    fixed_expenses,
    forecast,
    help_command,
    month_summary,
    set_budget,
    start,
    today_summary,
    unknown_command,
)
from app.config import get_settings
from app.database.session import init_db
from app.scheduler import start_daily_scheduler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


async def post_init(application: Application) -> None:
    start_daily_scheduler(application)


def build_application() -> Application:
    settings = get_settings()
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_expense))
    application.add_handler(CommandHandler("mes", month_summary))
    application.add_handler(CommandHandler("hoje", today_summary))
    application.add_handler(CommandHandler("dia", day_summary))
    application.add_handler(CommandHandler("grafico", category_chart))
    application.add_handler(CommandHandler("edit", edit_expense))
    application.add_handler(CommandHandler("delete", delete_expense))
    application.add_handler(CommandHandler(["receita", "receitas"], add_income))
    application.add_handler(CommandHandler("saldo", balance))
    application.add_handler(CommandHandler("orcamento", set_budget))
    application.add_handler(CommandHandler("previsao", forecast))
    application.add_handler(CommandHandler("comparar", compare_months))
    application.add_handler(CommandHandler("fixo", add_fixed_expense))
    application.add_handler(CommandHandler("fixos", fixed_expenses))
    application.add_handler(CommandHandler("delete_fixo", delete_fixed_expense))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    return application


def main() -> None:
    init_db()
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()

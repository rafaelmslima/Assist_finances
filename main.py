import logging

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot.conversations import build_conversation_handlers, cancel_conversation
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
from app.config import get_database_url, get_settings
from app.database.session import init_db
from app.scheduler import start_daily_scheduler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Iniciar o bot e cadastrar usuario"),
            BotCommand("help", "Ver ajuda e exemplos"),
            BotCommand("add", "Adicionar gasto: valor, categoria e descricao"),
            BotCommand("mes", "Ver resumo de gastos do mes"),
            BotCommand("hoje", "Ver gastos de hoje"),
            BotCommand("dia", "Ver gastos de um dia especifico"),
            BotCommand("grafico", "Ver grafico por categoria"),
            BotCommand("edit", "Editar um gasto pelo ID"),
            BotCommand("delete", "Apagar um gasto pelo ID"),
            BotCommand("receita", "Adicionar uma receita"),
            BotCommand("saldo", "Ver saldo atual e projetado"),
            BotCommand("orcamento", "Definir orcamento mensal ou por categoria"),
            BotCommand("previsao", "Ver previsao de gastos do mes"),
            BotCommand("comparar", "Comparar mes atual com anterior"),
            BotCommand("fixo", "Adicionar gasto fixo mensal"),
            BotCommand("fixos", "Listar gastos fixos"),
            BotCommand("delete_fixo", "Apagar gasto fixo pelo ID"),
            BotCommand("cancelar", "Cancelar fluxo guiado em andamento"),
        ]
    )
    start_daily_scheduler(application)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Erro nao tratado no bot", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Tive um erro interno ao processar esse comando. Tente novamente em instantes."
        )


def build_application() -> Application:
    settings = get_settings()
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    for conversation_handler in build_conversation_handlers():
        application.add_handler(conversation_handler)

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
    application.add_handler(CommandHandler("cancelar", cancel_conversation))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_error_handler(error_handler)

    return application


def main() -> None:
    database_backend = "sqlite" if get_database_url().startswith("sqlite") else "postgresql"
    logger.info("Iniciando Finance Bot com banco %s.", database_backend)
    init_db()
    application = build_application()
    logger.info("Polling do Telegram iniciando.")
    application.run_polling()


if __name__ == "__main__":
    main()

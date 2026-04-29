from telegram import Update
from telegram.ext import ContextTypes

from app.bot.keyboards import (
    CHART_BACK_CALLBACK,
    CHART_CLOSE_CALLBACK,
    CHART_PREFIX,
    build_chart_menu_keyboard,
    build_chart_result_keyboard,
)
from app.bot.commands import (
    HELP_TEXT,
    START_TEXT,
    format_balance,
    format_budget_saved,
    format_comparison,
    format_day_summary,
    format_expense_saved,
    format_fixed_expense_saved,
    format_fixed_expenses,
    format_forecast,
    format_broadcast_result,
    format_income_saved,
    format_month_summary,
)
from app.config import get_settings
from app.database.repository import (
    BudgetRepository,
    ExpenseRepository,
    FixedExpenseRepository,
    IncomeRepository,
    UpdateBroadcastRepository,
    UserRepository,
)
from app.database.session import SessionLocal
from app.database.models import User
from app.services.analytics_service import AnalyticsService
from app.services.broadcast_service import BroadcastService
from app.services.budget_service import BudgetService
from app.services.chart_report_service import ChartReportService
from app.services.expense_service import ExpenseService
from app.services.fixed_expense_service import FixedExpenseService
from app.services.income_service import IncomeService
from app.services.report_service import ReportService
from app.services.user_service import TelegramUserData, UnauthorizedUserError, UserService
from app.utils.validators import (
    ExpenseValidationError,
    parse_add_command,
    parse_budget_command,
    parse_day_command,
    parse_delete_command,
    parse_edit_command,
    parse_fixed_expense_command,
    parse_fixed_expense_id,
    parse_income_command,
)


UNAUTHORIZED_TEXT = "Voce nao esta autorizado a usar este bot."
BROADCAST_PERMISSION_DENIED_TEXT = "Voce nao tem permissao para usar este comando."


def _telegram_user_data(update: Update) -> TelegramUserData | None:
    telegram_user = update.effective_user
    chat = update.effective_chat
    if not telegram_user or not chat:
        return None

    return TelegramUserData(
        telegram_user_id=telegram_user.id,
        telegram_chat_id=chat.id,
        first_name=telegram_user.first_name,
        username=telegram_user.username,
    )


async def _get_or_register_user(update: Update) -> User | None:
    data = _telegram_user_data(update)
    message = update.effective_message
    if not data:
        if message:
            await message.reply_text("Nao consegui identificar seu usuario no Telegram.")
        return None

    try:
        with SessionLocal() as db:
            return UserService(UserRepository(db)).register_or_update_from_telegram(data)
    except UnauthorizedUserError:
        if message:
            await message.reply_text(UNAUTHORIZED_TEXT)
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return
    await update.message.reply_text(START_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


def _is_admin(telegram_user_id: int) -> bool:
    return telegram_user_id in get_settings().admin_telegram_ids


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user = update.effective_user
    if not telegram_user or not _is_admin(telegram_user.id):
        await update.message.reply_text(BROADCAST_PERMISSION_DENIED_TEXT)
        return

    message = " ".join(context.args).strip()
    if not message:
        await update.message.reply_text("Use: /broadcast mensagem")
        return

    with SessionLocal() as db:
        result = await BroadcastService(
            UserRepository(db),
            UpdateBroadcastRepository(db),
        ).send_update_broadcast(
            bot=context.bot,
            admin_user_id=telegram_user.id,
            message=message,
        )

    await update.message.reply_text(
        format_broadcast_result(result.total_users, result.sent_count, result.failed_count)
    )


async def updates_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        UserRepository(db).set_receive_updates_notifications(user.id, False)

    await update.message.reply_text("Notificacoes de novidades desativadas.")


async def updates_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        UserRepository(db).set_receive_updates_notifications(user.id, True)

    await update.message.reply_text("Notificacoes de novidades reativadas.")


async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        parsed_expense = parse_add_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
        return

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        expense = ExpenseService(repository).add_expense(user.id, parsed_expense)

    await update.message.reply_text(format_expense_saved(expense, "registrado"))


async def add_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        parsed_income = parse_income_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
        return

    with SessionLocal() as db:
        income = IncomeService(IncomeRepository(db)).add_income(user.id, parsed_income)

    await update.message.reply_text(format_income_saved(income))


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        analytics = AnalyticsService(
            ExpenseRepository(db),
            IncomeRepository(db),
            BudgetRepository(db),
            FixedExpenseRepository(db),
        )
        summary = analytics.get_balance(user.id)

    await update.message.reply_text(format_balance(summary))


async def set_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        parsed_budget = parse_budget_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
        return

    with SessionLocal() as db:
        budget_service = BudgetService(BudgetRepository(db), ExpenseRepository(db))
        budget_service.set_budget(user.id, parsed_budget)
        status = budget_service.get_budget_status(user.id)

    await update.message.reply_text(format_budget_saved(status))


async def forecast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        analytics = AnalyticsService(
            ExpenseRepository(db),
            IncomeRepository(db),
            BudgetRepository(db),
            FixedExpenseRepository(db),
        )
        result = analytics.get_forecast(user.id)

    await update.message.reply_text(format_forecast(result))


async def compare_months(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        analytics = AnalyticsService(
            ExpenseRepository(db),
            IncomeRepository(db),
            BudgetRepository(db),
            FixedExpenseRepository(db),
        )
        result = analytics.compare_with_previous_month(user.id)

    await update.message.reply_text(format_comparison(result))


async def add_fixed_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        parsed_fixed_expense = parse_fixed_expense_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
        return

    with SessionLocal() as db:
        fixed_expense = FixedExpenseService(FixedExpenseRepository(db)).add_fixed_expense(
            user.id,
            parsed_fixed_expense,
        )

    await update.message.reply_text(format_fixed_expense_saved(fixed_expense))


async def fixed_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        summary = FixedExpenseService(FixedExpenseRepository(db)).list_fixed_expenses(user.id)

    await update.message.reply_text(format_fixed_expenses(summary))


async def delete_fixed_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        fixed_expense_id = parse_fixed_expense_id(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
        return

    with SessionLocal() as db:
        deleted = FixedExpenseService(FixedExpenseRepository(db)).delete_fixed_expense(
            user.id,
            fixed_expense_id,
        )

    if not deleted:
        await update.message.reply_text("Gasto fixo nao encontrado para o seu usuario.")
        return

    await update.message.reply_text(f"Gasto fixo #{fixed_expense_id} apagado.")


async def edit_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        expense_id, parsed_expense = parse_edit_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
        return

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        expense = ExpenseService(repository).edit_expense(user.id, expense_id, parsed_expense)

    if not expense:
        await update.message.reply_text("Gasto nao encontrado para o seu usuario.")
        return

    await update.message.reply_text(format_expense_saved(expense, "atualizado"))


async def delete_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        expense_id = parse_delete_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
        return

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        deleted = ExpenseService(repository).delete_expense(user.id, expense_id)

    if not deleted:
        await update.message.reply_text("Gasto nao encontrado para o seu usuario.")
        return

    await update.message.reply_text(f"Gasto #{expense_id} apagado.")


async def month_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        summary = ReportService(repository).get_current_month_summary(user.id)

    await update.message.reply_text(format_month_summary(summary))


async def today_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = []
    await day_summary(update, context)


async def day_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        target_date = parse_day_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
        return

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        summary = ReportService(repository).get_day_summary(user.id, target_date)

    await update.message.reply_text(format_day_summary(summary))


async def chart_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    await update.message.reply_text(
        "Que gráfico você quer ver?",
        reply_markup=build_chart_menu_keyboard(),
    )


async def chart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = query.data or ""

    if data == CHART_CLOSE_CALLBACK:
        await query.edit_message_text("Menu de gráficos fechado.")
        return

    if data == CHART_BACK_CALLBACK:
        await query.edit_message_text(
            "Que gráfico você quer ver?",
            reply_markup=build_chart_menu_keyboard(),
        )
        return

    if not data.startswith(f"{CHART_PREFIX}:show:"):
        await query.edit_message_text("Opcao de grafico invalida.")
        return

    user = await _get_or_register_user(update)
    if not user:
        return

    chart_type = data.rsplit(":", 1)[1]
    with SessionLocal() as db:
        report = ChartReportService(
            ExpenseRepository(db),
            BudgetRepository(db),
            FixedExpenseRepository(db),
        ).build(user.id, chart_type)

    if report.chart:
        await query.message.reply_photo(photo=report.chart, caption=report.text)
    else:
        await query.message.reply_text(report.text)

    await query.message.reply_text(
        "O que deseja fazer agora?",
        reply_markup=build_chart_result_keyboard(),
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Comando nao reconhecido. Use /help para ver os comandos disponiveis."
    )

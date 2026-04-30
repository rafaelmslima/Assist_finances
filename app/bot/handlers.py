from telegram import Update
from telegram.ext import ContextTypes

from app.bot.keyboards import (
    CHART_BACK_CALLBACK,
    CHART_CLOSE_CALLBACK,
    CHART_PREFIX,
    RECURRING_FIXED_NO_CALLBACK,
    RECURRING_FIXED_YES_CALLBACK,
    build_chart_menu_keyboard,
    build_chart_result_keyboard,
    build_main_reply_keyboard,
    build_recurring_fixed_expense_keyboard,
)
from app.bot.commands import (
    HELP_TEXT,
    START_TEXT,
    format_budget_saved,
    format_comparison,
    format_available_daily,
    format_day_summary,
    format_expense_saved,
    format_fixed_expense_saved,
    format_fixed_expenses,
    format_forecast,
    format_broadcast_result,
    format_income_saved,
    format_month_summary,
    format_recurring_expense_suggestion,
    format_salary_saved,
    format_smart_summary,
    format_spending_insights,
)
from app.config import get_settings
from app.database.repository import (
    BudgetRepository,
    ExpenseRepository,
    FixedExpenseRepository,
    IncomeRepository,
    SalaryConfigRepository,
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
from app.services.recurring_expense_service import RecurringExpenseService
from app.services.report_service import ReportService
from app.services.salary_service import SalaryService, schedule_label
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
    parse_amount,
    ParsedFixedExpense,
    validate_broadcast_message,
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
    await update.message.reply_text(START_TEXT, reply_markup=build_main_reply_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, reply_markup=build_main_reply_keyboard())


def _is_admin(telegram_user_id: int) -> bool:
    return telegram_user_id in get_settings().admin_telegram_ids


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user = update.effective_user
    if not telegram_user or not _is_admin(telegram_user.id):
        await update.message.reply_text(BROADCAST_PERMISSION_DENIED_TEXT)
        return

    try:
        message = validate_broadcast_message(" ".join(context.args))
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
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

    await update.message.reply_text(
        "Notificacoes de novidades desativadas.",
        reply_markup=build_main_reply_keyboard(),
    )


async def updates_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        UserRepository(db).set_receive_updates_notifications(user.id, True)

    await update.message.reply_text(
        "Notificacoes de novidades reativadas.",
        reply_markup=build_main_reply_keyboard(),
    )


async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        parsed_expense = parse_add_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc), reply_markup=build_main_reply_keyboard())
        return

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        expense = ExpenseService(repository).add_expense(user.id, parsed_expense)

    await update.message.reply_text(
        format_expense_saved(expense, "registrado"),
        reply_markup=build_main_reply_keyboard(),
    )
    await _send_recurring_expense_suggestion(update.message, user.id, expense)


async def add_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        parsed_income = parse_income_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc), reply_markup=build_main_reply_keyboard())
        return

    with SessionLocal() as db:
        income = IncomeService(IncomeRepository(db)).add_income(user.id, parsed_income)

    await update.message.reply_text(format_income_saved(income), reply_markup=build_main_reply_keyboard())


async def set_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    if not context.args:
        await update.message.reply_text(
            "Use /salario valor ou toque em Salario para configurar passo a passo.\nExemplo: /salario 3500",
            reply_markup=build_main_reply_keyboard(),
        )
        return

    try:
        amount = parse_amount(context.args[0], command="/salario")
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc), reply_markup=build_main_reply_keyboard())
        return

    with SessionLocal() as db:
        salary_config, _income = SalaryService(
            SalaryConfigRepository(db),
            IncomeRepository(db),
        ).register_manual_salary(user.id, amount)

    await update.message.reply_text(
        format_salary_saved(
            salary_config.amount,
            schedule_label(salary_config.schedule_type, salary_config.pay_day),
        ),
        reply_markup=build_main_reply_keyboard(),
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await smart_summary(update, context)


async def available_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        analytics = AnalyticsService(
            ExpenseRepository(db),
            IncomeRepository(db),
            BudgetRepository(db),
            FixedExpenseRepository(db),
            SalaryConfigRepository(db),
        )
        available = analytics.get_available_daily_amount(user.id)

    await update.message.reply_text(
        format_available_daily(available),
        reply_markup=build_main_reply_keyboard(),
    )


async def smart_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        analytics = AnalyticsService(
            ExpenseRepository(db),
            IncomeRepository(db),
            BudgetRepository(db),
            FixedExpenseRepository(db),
            SalaryConfigRepository(db),
        )
        summary = analytics.get_smart_summary(user.id)

    await update.message.reply_text(
        format_smart_summary(summary),
        reply_markup=build_main_reply_keyboard(),
    )


async def set_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        parsed_budget = parse_budget_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc), reply_markup=build_main_reply_keyboard())
        return

    with SessionLocal() as db:
        budget_service = BudgetService(BudgetRepository(db), ExpenseRepository(db), SalaryConfigRepository(db))
        budget_service.set_budget(user.id, parsed_budget)
        status = budget_service.get_budget_status(user.id)

    await update.message.reply_text(format_budget_saved(status), reply_markup=build_main_reply_keyboard())


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
            SalaryConfigRepository(db),
        )
        result = analytics.get_forecast(user.id)

    await update.message.reply_text(format_forecast(result), reply_markup=build_main_reply_keyboard())


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
            SalaryConfigRepository(db),
        )
        result = analytics.compare_with_previous_month(user.id)

    await update.message.reply_text(format_comparison(result), reply_markup=build_main_reply_keyboard())


async def spending_insights(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        analytics = AnalyticsService(
            ExpenseRepository(db),
            IncomeRepository(db),
            BudgetRepository(db),
            FixedExpenseRepository(db),
            SalaryConfigRepository(db),
        )
        result = analytics.get_spending_insights(user.id)

    await update.message.reply_text(
        format_spending_insights(result),
        reply_markup=build_main_reply_keyboard(),
    )


async def add_fixed_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        parsed_fixed_expense = parse_fixed_expense_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc), reply_markup=build_main_reply_keyboard())
        return

    with SessionLocal() as db:
        fixed_expense = FixedExpenseService(FixedExpenseRepository(db)).add_fixed_expense(
            user.id,
            parsed_fixed_expense,
        )

    await update.message.reply_text(
        format_fixed_expense_saved(fixed_expense),
        reply_markup=build_main_reply_keyboard(),
    )


async def fixed_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        summary = FixedExpenseService(FixedExpenseRepository(db)).list_fixed_expenses(user.id)

    await update.message.reply_text(format_fixed_expenses(summary), reply_markup=build_main_reply_keyboard())


async def delete_fixed_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        fixed_expense_id = parse_fixed_expense_id(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc), reply_markup=build_main_reply_keyboard())
        return

    with SessionLocal() as db:
        deleted = FixedExpenseService(FixedExpenseRepository(db)).delete_fixed_expense(
            user.id,
            fixed_expense_id,
        )

    if not deleted:
        await update.message.reply_text(
            "Gasto fixo nao encontrado para o seu usuario.",
            reply_markup=build_main_reply_keyboard(),
        )
        return

    await update.message.reply_text(
        f"Gasto fixo #{fixed_expense_id} apagado.",
        reply_markup=build_main_reply_keyboard(),
    )


async def edit_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        expense_id, parsed_expense = parse_edit_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc), reply_markup=build_main_reply_keyboard())
        return

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        expense = ExpenseService(repository).edit_expense(user.id, expense_id, parsed_expense)

    if not expense:
        await update.message.reply_text(
            "Gasto nao encontrado para o seu usuario.",
            reply_markup=build_main_reply_keyboard(),
        )
        return

    await update.message.reply_text(
        format_expense_saved(expense, "atualizado"),
        reply_markup=build_main_reply_keyboard(),
    )


async def delete_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    try:
        expense_id = parse_delete_command(context.args)
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc), reply_markup=build_main_reply_keyboard())
        return

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        deleted = ExpenseService(repository).delete_expense(user.id, expense_id)

    if not deleted:
        await update.message.reply_text(
            "Gasto nao encontrado para o seu usuario.",
            reply_markup=build_main_reply_keyboard(),
        )
        return

    await update.message.reply_text(
        f"Gasto #{expense_id} apagado.",
        reply_markup=build_main_reply_keyboard(),
    )


async def month_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await _get_or_register_user(update)
    if not user:
        return

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        summary = ReportService(repository, SalaryConfigRepository(db)).get_current_month_summary(user.id)

    await update.message.reply_text(format_month_summary(summary), reply_markup=build_main_reply_keyboard())


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
        await update.message.reply_text(str(exc), reply_markup=build_main_reply_keyboard())
        return

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        summary = ReportService(repository).get_day_summary(user.id, target_date)

    await update.message.reply_text(format_day_summary(summary), reply_markup=build_main_reply_keyboard())


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


async def recurring_fixed_expense_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer()
    user = await _get_or_register_user(update)
    if not user:
        return

    data = query.data or ""
    try:
        action, expense_id_text = data.rsplit(":", 1)
        expense_id = int(expense_id_text)
    except ValueError:
        await query.edit_message_text("Opcao de gasto recorrente invalida.")
        return

    if action == RECURRING_FIXED_NO_CALLBACK:
        await query.edit_message_text("Tudo bem. Nao adicionei esse gasto como fixo.")
        return

    if action != RECURRING_FIXED_YES_CALLBACK:
        await query.edit_message_text("Opcao de gasto recorrente invalida.")
        return

    with SessionLocal() as db:
        expense_repository = ExpenseRepository(db)
        fixed_repository = FixedExpenseRepository(db)
        expense = expense_repository.get_by_id(user.id, expense_id)
        if not expense:
            await query.edit_message_text("Nao encontrei esse gasto para adicionar como fixo.")
            return

        recurring_service = RecurringExpenseService(expense_repository, fixed_repository)
        if recurring_service.has_similar_fixed_expense(user.id, expense):
            await query.edit_message_text("Esse gasto fixo ja existe na sua lista.")
            return

        fixed_expense = FixedExpenseService(fixed_repository).add_fixed_expense(
            user.id,
            ParsedFixedExpense(
                amount=expense.amount,
                category=expense.category,
                description=expense.description,
            ),
        )

    await query.edit_message_text(format_fixed_expense_saved(fixed_expense))


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Comando nao reconhecido. Use /help para ver os comandos disponiveis.",
        reply_markup=build_main_reply_keyboard(),
    )


async def _send_recurring_expense_suggestion(message, user_id: int, expense) -> None:
    with SessionLocal() as db:
        suggestion = RecurringExpenseService(
            ExpenseRepository(db),
            FixedExpenseRepository(db),
        ).detect_for_expense(user_id, expense)

    if not suggestion:
        return

    await message.reply_text(
        format_recurring_expense_suggestion(suggestion),
        reply_markup=build_recurring_fixed_expense_keyboard(suggestion.expense_id),
    )

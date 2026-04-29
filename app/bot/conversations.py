from enum import IntEnum

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from app.bot.commands import (
    format_budget_saved,
    format_currency,
    format_expense_saved,
    format_fixed_expense_saved,
    format_income_saved,
)
from app.bot.handlers import (
    _get_or_register_user,
    add_expense,
    add_fixed_expense,
    add_income,
    set_budget,
)
from app.bot.keyboards import (
    CANCEL_EXPENSE_CALLBACK,
    CATEGORY_PREFIX,
    CONFIRM_EXPENSE_CALLBACK,
    NEW_CATEGORY_CALLBACK,
    OTHER_CATEGORY_CALLBACK,
    build_expense_category_keyboard,
    build_expense_confirmation_keyboard,
)
from app.database.repository import BudgetRepository, ExpenseRepository, FixedExpenseRepository, IncomeRepository
from app.database.session import SessionLocal
from app.services.budget_service import BudgetService
from app.services.expense_service import ExpenseService
from app.services.fixed_expense_service import FixedExpenseService
from app.services.income_service import IncomeService
from app.services.report_service import ReportService
from app.utils.validators import (
    ExpenseValidationError,
    ParsedBudget,
    ParsedExpense,
    ParsedFixedExpense,
    ParsedIncome,
    parse_amount,
    validate_category,
    validate_description,
)


class State(IntEnum):
    ADD_AMOUNT = 1
    ADD_CATEGORY = 2
    ADD_DESCRIPTION = 3
    ADD_NEW_CATEGORY = 4
    ADD_CONFIRM = 5
    INCOME_AMOUNT = 6
    INCOME_DESCRIPTION = 7
    FIXED_AMOUNT = 8
    FIXED_CATEGORY = 9
    FIXED_DESCRIPTION = 10
    BUDGET_CATEGORY = 11
    BUDGET_AMOUNT = 12


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("guided", None)
    await update.message.reply_text("Fluxo cancelado. Use /help para ver exemplos.")
    return ConversationHandler.END


async def start_add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await add_expense(update, context)
        return ConversationHandler.END

    user = await _get_or_register_user(update)
    if not user:
        return ConversationHandler.END

    context.user_data["guided"] = {"type": "expense", "user_id": user.id}
    await update.message.reply_text("Qual o valor do gasto? Exemplo: 25,90\n\nUse /cancelar para cancelar.")
    return State.ADD_AMOUNT


async def receive_add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = parse_amount(update.message.text.strip(), command="/add")
    except ExpenseValidationError as exc:
        await update.message.reply_text(f"{exc}\n\nDigite o valor novamente ou use /cancelar.")
        return State.ADD_AMOUNT

    context.user_data["guided"]["amount"] = amount
    with SessionLocal() as db:
        categories = ExpenseService(ExpenseRepository(db)).get_user_expense_categories(
            context.user_data["guided"]["user_id"]
        )

    context.user_data["guided"]["categories"] = categories
    await update.message.reply_text(
        "Escolha uma categoria:",
        reply_markup=build_expense_category_keyboard(categories),
    )
    return State.ADD_CATEGORY


async def receive_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await receive_new_add_category(update, context)


async def choose_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    guided = context.user_data.get("guided", {})
    categories = guided.get("categories", [])

    if data == NEW_CATEGORY_CALLBACK:
        await query.edit_message_text("Qual o nome da nova categoria? Exemplo: mercado")
        return State.ADD_NEW_CATEGORY

    if data == OTHER_CATEGORY_CALLBACK:
        guided["category"] = "outros"
        await query.edit_message_text("Categoria escolhida: Outros")
        await query.message.reply_text("Descricao opcional.\nEnvie uma descricao ou digite /pular.")
        return State.ADD_DESCRIPTION

    if data.startswith(f"{CATEGORY_PREFIX}:page:"):
        page = int(data.rsplit(":", 1)[1])
        await query.edit_message_reply_markup(reply_markup=build_expense_category_keyboard(categories, page))
        return State.ADD_CATEGORY

    if data.startswith(f"{CATEGORY_PREFIX}:select:"):
        category_index = int(data.rsplit(":", 1)[1])
        if category_index < 0 or category_index >= len(categories):
            await query.edit_message_text("Categoria invalida. Digite /add para iniciar novamente.")
            context.user_data.pop("guided", None)
            return ConversationHandler.END

        category = categories[category_index]
        guided["category"] = category
        await query.edit_message_text(f"Categoria escolhida: {category}")
        await query.message.reply_text("Descricao opcional.\nEnvie uma descricao ou digite /pular.")
        return State.ADD_DESCRIPTION

    await query.edit_message_text("Opcao invalida. Digite /add para iniciar novamente.")
    context.user_data.pop("guided", None)
    return ConversationHandler.END


async def receive_new_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        category = validate_category(update.message.text, command="/add")
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
        return State.ADD_NEW_CATEGORY

    context.user_data["guided"]["category"] = category
    await update.message.reply_text("Descricao opcional? Envie um texto ou digite /pular.")
    return State.ADD_DESCRIPTION


async def receive_add_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["guided"]["description"] = validate_description(update.message.text.strip() or None)
    except ExpenseValidationError as exc:
        await update.message.reply_text(f"{exc}\n\nEnvie outra descricao ou digite /pular.")
        return State.ADD_DESCRIPTION
    await _send_expense_confirmation(update, context)
    return State.ADD_CONFIRM


async def _send_expense_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.user_data["guided"]
    description = data.get("description") or "sem descricao"
    await update.message.reply_text(
        "\n".join(
            [
                "Confirmar gasto?",
                "",
                f"Valor: {format_currency(float(data['amount']))}",
                f"Categoria: {data['category']}",
                f"Descricao: {description}",
            ]
        ),
        reply_markup=build_expense_confirmation_keyboard(),
    )


async def confirm_add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == CANCEL_EXPENSE_CALLBACK:
        context.user_data.pop("guided", None)
        await query.edit_message_text("Fluxo cancelado. Nenhum gasto foi salvo.")
        return ConversationHandler.END

    if query.data != CONFIRM_EXPENSE_CALLBACK:
        await query.edit_message_text("Opcao invalida. Digite /add para iniciar novamente.")
        context.user_data.pop("guided", None)
        return ConversationHandler.END

    data = context.user_data.pop("guided")
    parsed = ParsedExpense(
        amount=data["amount"],
        category=data["category"],
        description=data.get("description"),
    )

    with SessionLocal() as db:
        repository = ExpenseRepository(db)
        expense = ExpenseService(repository).add_expense(data["user_id"], parsed)
        summary = ReportService(repository).get_current_month_summary(data["user_id"])

    await query.edit_message_text(
        f"{format_expense_saved(expense, 'registrado')}\n"
        f"Total gasto no mes: {format_currency(float(summary['total']))}."
    )
    return ConversationHandler.END


async def skip_add_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["guided"]["description"] = None
    await _send_expense_confirmation(update, context)
    return State.ADD_CONFIRM


async def start_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await add_income(update, context)
        return ConversationHandler.END

    user = await _get_or_register_user(update)
    if not user:
        return ConversationHandler.END

    context.user_data["guided"] = {"type": "income", "user_id": user.id}
    await update.message.reply_text("Qual o valor da receita? Exemplo: 3000\n\nUse /cancelar para cancelar.")
    return State.INCOME_AMOUNT


async def receive_income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = parse_amount(update.message.text.strip(), command="/receita")
    except ExpenseValidationError as exc:
        await update.message.reply_text(f"{exc}\n\nDigite o valor novamente ou use /cancelar.")
        return State.INCOME_AMOUNT

    context.user_data["guided"]["amount"] = amount
    await update.message.reply_text("Descricao opcional? Exemplo: salario. Envie um texto ou digite /pular.")
    return State.INCOME_DESCRIPTION


async def receive_income_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        description = validate_description(update.message.text.strip() or None)
    except ExpenseValidationError as exc:
        await update.message.reply_text(f"{exc}\n\nEnvie outra descricao ou digite /pular.")
        return State.INCOME_DESCRIPTION
    return await _save_guided_income(update, context, description)


async def _save_guided_income(update: Update, context: ContextTypes.DEFAULT_TYPE, description: str | None) -> int:
    data = context.user_data.pop("guided")
    parsed = ParsedIncome(amount=data["amount"], description=description)

    with SessionLocal() as db:
        income = IncomeService(IncomeRepository(db)).add_income(data["user_id"], parsed)

    await update.message.reply_text(format_income_saved(income))
    return ConversationHandler.END


async def skip_income_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_guided_income(update, context, None)


async def start_fixed_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await add_fixed_expense(update, context)
        return ConversationHandler.END

    user = await _get_or_register_user(update)
    if not user:
        return ConversationHandler.END

    context.user_data["guided"] = {"type": "fixed_expense", "user_id": user.id}
    await update.message.reply_text("Qual o valor do gasto fixo? Exemplo: 120\n\nUse /cancelar para cancelar.")
    return State.FIXED_AMOUNT


async def receive_fixed_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = parse_amount(update.message.text.strip(), command="/fixo")
    except ExpenseValidationError as exc:
        await update.message.reply_text(f"{exc}\n\nDigite o valor novamente ou use /cancelar.")
        return State.FIXED_AMOUNT

    context.user_data["guided"]["amount"] = amount
    await update.message.reply_text("Qual a categoria? Exemplo: academia")
    return State.FIXED_CATEGORY


async def receive_fixed_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        category = validate_category(update.message.text, command="/fixo")
    except ExpenseValidationError as exc:
        await update.message.reply_text(str(exc))
        return State.FIXED_CATEGORY

    context.user_data["guided"]["category"] = category
    await update.message.reply_text("Descricao opcional? Envie um texto ou digite /pular.")
    return State.FIXED_DESCRIPTION


async def receive_fixed_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        description = validate_description(update.message.text.strip() or None)
    except ExpenseValidationError as exc:
        await update.message.reply_text(f"{exc}\n\nEnvie outra descricao ou digite /pular.")
        return State.FIXED_DESCRIPTION
    return await _save_guided_fixed_expense(update, context, description)


async def _save_guided_fixed_expense(update: Update, context: ContextTypes.DEFAULT_TYPE, description: str | None) -> int:
    data = context.user_data.pop("guided")
    parsed = ParsedFixedExpense(
        amount=data["amount"],
        category=data["category"],
        description=description,
    )

    with SessionLocal() as db:
        fixed_expense = FixedExpenseService(FixedExpenseRepository(db)).add_fixed_expense(
            data["user_id"],
            parsed,
        )

    await update.message.reply_text(format_fixed_expense_saved(fixed_expense))
    return ConversationHandler.END


async def skip_fixed_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_guided_fixed_expense(update, context, None)


async def start_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await set_budget(update, context)
        return ConversationHandler.END

    user = await _get_or_register_user(update)
    if not user:
        return ConversationHandler.END

    context.user_data["guided"] = {"type": "budget", "user_id": user.id}
    await update.message.reply_text(
        "Esse orcamento e total ou por categoria?\n"
        "Digite total ou o nome da categoria. Exemplo: alimentacao\n\n"
        "Use /cancelar para cancelar."
    )
    return State.BUDGET_CATEGORY


async def receive_budget_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_category = update.message.text.strip()
    if not raw_category:
        await update.message.reply_text("Digite total ou uma categoria. Exemplo: transporte")
        return State.BUDGET_CATEGORY

    if raw_category.lower() == "total":
        context.user_data["guided"]["category"] = None
    else:
        try:
            context.user_data["guided"]["category"] = validate_category(raw_category, command="/orcamento")
        except ExpenseValidationError as exc:
            await update.message.reply_text(str(exc))
            return State.BUDGET_CATEGORY
    await update.message.reply_text("Qual o valor do orcamento? Exemplo: 600")
    return State.BUDGET_AMOUNT


async def receive_budget_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = parse_amount(update.message.text.strip(), command="/orcamento")
    except ExpenseValidationError as exc:
        await update.message.reply_text(f"{exc}\n\nDigite o valor novamente ou use /cancelar.")
        return State.BUDGET_AMOUNT

    data = context.user_data.pop("guided")
    parsed = ParsedBudget(amount=amount, category=data["category"])

    with SessionLocal() as db:
        budget_service = BudgetService(BudgetRepository(db), ExpenseRepository(db))
        budget_service.set_budget(data["user_id"], parsed)
        status = budget_service.get_budget_status(data["user_id"])

    await update.message.reply_text(format_budget_saved(status))
    return ConversationHandler.END


def build_conversation_handlers() -> list[ConversationHandler]:
    text_filter = filters.TEXT & ~filters.COMMAND
    return [
        ConversationHandler(
            entry_points=[CommandHandler("add", start_add_expense)],
            states={
                State.ADD_AMOUNT: [MessageHandler(text_filter, receive_add_amount)],
                State.ADD_CATEGORY: [
                    CallbackQueryHandler(choose_add_category, pattern=f"^{CATEGORY_PREFIX}:"),
                    MessageHandler(text_filter, receive_add_category),
                ],
                State.ADD_NEW_CATEGORY: [MessageHandler(text_filter, receive_new_add_category)],
                State.ADD_DESCRIPTION: [
                    CommandHandler("pular", skip_add_description),
                    MessageHandler(text_filter, receive_add_description),
                ],
                State.ADD_CONFIRM: [
                    CallbackQueryHandler(
                        confirm_add_expense,
                        pattern=f"^({CONFIRM_EXPENSE_CALLBACK}|{CANCEL_EXPENSE_CALLBACK})$",
                    )
                ],
            },
            fallbacks=[CommandHandler("cancelar", cancel_conversation)],
        ),
        ConversationHandler(
            entry_points=[CommandHandler(["receita", "receitas"], start_income)],
            states={
                State.INCOME_AMOUNT: [MessageHandler(text_filter, receive_income_amount)],
                State.INCOME_DESCRIPTION: [
                    CommandHandler("pular", skip_income_description),
                    MessageHandler(text_filter, receive_income_description),
                ],
            },
            fallbacks=[CommandHandler("cancelar", cancel_conversation)],
        ),
        ConversationHandler(
            entry_points=[CommandHandler("fixo", start_fixed_expense)],
            states={
                State.FIXED_AMOUNT: [MessageHandler(text_filter, receive_fixed_amount)],
                State.FIXED_CATEGORY: [MessageHandler(text_filter, receive_fixed_category)],
                State.FIXED_DESCRIPTION: [
                    CommandHandler("pular", skip_fixed_description),
                    MessageHandler(text_filter, receive_fixed_description),
                ],
            },
            fallbacks=[CommandHandler("cancelar", cancel_conversation)],
        ),
        ConversationHandler(
            entry_points=[CommandHandler("orcamento", start_budget)],
            states={
                State.BUDGET_CATEGORY: [MessageHandler(text_filter, receive_budget_category)],
                State.BUDGET_AMOUNT: [MessageHandler(text_filter, receive_budget_amount)],
            },
            fallbacks=[CommandHandler("cancelar", cancel_conversation)],
        ),
    ]

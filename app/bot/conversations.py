from enum import IntEnum

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from app.bot.commands import (
    format_budget_saved,
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
from app.database.repository import BudgetRepository, ExpenseRepository, FixedExpenseRepository, IncomeRepository
from app.database.session import SessionLocal
from app.services.budget_service import BudgetService
from app.services.expense_service import ExpenseService
from app.services.fixed_expense_service import FixedExpenseService
from app.services.income_service import IncomeService
from app.utils.validators import (
    ExpenseValidationError,
    ParsedBudget,
    ParsedExpense,
    ParsedFixedExpense,
    ParsedIncome,
    parse_amount,
)


class State(IntEnum):
    ADD_AMOUNT = 1
    ADD_CATEGORY = 2
    ADD_DESCRIPTION = 3
    INCOME_AMOUNT = 4
    INCOME_DESCRIPTION = 5
    FIXED_AMOUNT = 6
    FIXED_CATEGORY = 7
    FIXED_DESCRIPTION = 8
    BUDGET_CATEGORY = 9
    BUDGET_AMOUNT = 10


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
    await update.message.reply_text("Qual a categoria? Exemplo: mercado")
    return State.ADD_CATEGORY


async def receive_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    category = update.message.text.strip().lower()
    if not category:
        await update.message.reply_text("Informe uma categoria. Exemplo: alimentacao")
        return State.ADD_CATEGORY

    context.user_data["guided"]["category"] = category
    await update.message.reply_text("Descricao opcional? Envie um texto ou digite /pular.")
    return State.ADD_DESCRIPTION


async def receive_add_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_guided_expense(update, context, update.message.text.strip() or None)


async def _save_guided_expense(update: Update, context: ContextTypes.DEFAULT_TYPE, description: str | None) -> int:
    data = context.user_data.pop("guided")
    parsed = ParsedExpense(
        amount=data["amount"],
        category=data["category"],
        description=description,
    )

    with SessionLocal() as db:
        expense = ExpenseService(ExpenseRepository(db)).add_expense(data["user_id"], parsed)

    await update.message.reply_text(format_expense_saved(expense, "registrado"))
    return ConversationHandler.END


async def skip_add_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_guided_expense(update, context, None)


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
    return await _save_guided_income(update, context, update.message.text.strip() or None)


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
    category = update.message.text.strip().lower()
    if not category:
        await update.message.reply_text("Informe uma categoria. Exemplo: moradia")
        return State.FIXED_CATEGORY

    context.user_data["guided"]["category"] = category
    await update.message.reply_text("Descricao opcional? Envie um texto ou digite /pular.")
    return State.FIXED_DESCRIPTION


async def receive_fixed_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _save_guided_fixed_expense(update, context, update.message.text.strip() or None)


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
    raw_category = update.message.text.strip().lower()
    if not raw_category:
        await update.message.reply_text("Digite total ou uma categoria. Exemplo: transporte")
        return State.BUDGET_CATEGORY

    context.user_data["guided"]["category"] = None if raw_category == "total" else raw_category
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
                State.ADD_CATEGORY: [MessageHandler(text_filter, receive_add_category)],
                State.ADD_DESCRIPTION: [
                    CommandHandler("pular", skip_add_description),
                    MessageHandler(text_filter, receive_add_description),
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

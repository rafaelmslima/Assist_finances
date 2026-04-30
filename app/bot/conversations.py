from enum import IntEnum

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from app.bot.commands import (
    START_TEXT,
    format_budget_saved,
    format_currency,
    format_expense_saved,
    format_fixed_expense_saved,
    format_income_saved,
    format_salary_saved,
)
from app.bot.handlers import (
    _get_or_register_user,
    _send_recurring_expense_suggestion,
    add_expense,
    add_fixed_expense,
    add_income,
    set_budget,
)
from app.bot.keyboards import (
    CANCEL_EXPENSE_CALLBACK,
    CATEGORY_PREFIX,
    CONFIRM_EXPENSE_CALLBACK,
    MAIN_BUTTON_ADD_EXPENSE,
    MAIN_BUTTON_SALARY,
    NEW_CATEGORY_CALLBACK,
    ONBOARDING_NO,
    ONBOARDING_ONE_TICKET,
    ONBOARDING_TICKET_FOOD,
    ONBOARDING_TICKET_MEAL,
    ONBOARDING_TWO_TICKETS,
    ONBOARDING_YES,
    OTHER_CATEGORY_CALLBACK,
    PAYMENT_MONEY_CALLBACK,
    PAYMENT_PREFIX,
    PAYMENT_TICKET_FOOD_CALLBACK,
    PAYMENT_TICKET_MEAL_CALLBACK,
    build_expense_category_keyboard,
    build_expense_confirmation_keyboard,
    build_main_reply_keyboard,
    build_payment_source_keyboard,
    build_ticket_count_keyboard,
    build_ticket_type_keyboard,
    build_yes_no_keyboard,
)
from app.database.repository import BudgetRepository, ExpenseRepository, FixedExpenseRepository, IncomeRepository, SalaryConfigRepository, TicketBenefitRepository, UserRepository
from app.database.session import SessionLocal
from app.services.budget_service import BudgetService
from app.services.expense_service import ExpenseService
from app.services.fixed_expense_service import FixedExpenseService
from app.services.income_service import IncomeService
from app.services.report_service import ReportService
from app.services.salary_service import ParsedSalary, SalaryService, SCHEDULE_FIFTH_BUSINESS_DAY, SCHEDULE_FIXED_DAY, schedule_label
from app.services.ticket_service import (
    BENEFIT_ALIMENTACAO,
    BENEFIT_REFEICAO,
    PAYMENT_MONEY,
    PAYMENT_TICKET_ALIMENTACAO,
    PAYMENT_TICKET_REFEICAO,
    TicketBalanceError,
    TicketService,
)
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
    SALARY_AMOUNT = 13
    SALARY_SCHEDULE = 14
    SALARY_PAY_DAY = 15
    ADD_PAYMENT_SOURCE = 16
    ONBOARDING_SALARY_CHOICE = 17
    ONBOARDING_TICKET_CHOICE = 18
    ONBOARDING_TICKET_COUNT = 19
    ONBOARDING_TICKET_TYPE = 20
    ONBOARDING_TICKET_AMOUNT = 21


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("guided", None)
    await update.message.reply_text("Fluxo cancelado. Use /help para ver exemplos.")
    return ConversationHandler.END


async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await _get_or_register_user(update)
    if not user:
        return ConversationHandler.END
    if user.onboarding_completed:
        await update.message.reply_text(START_TEXT, reply_markup=build_main_reply_keyboard())
        return ConversationHandler.END

    context.user_data["guided"] = {"type": "onboarding", "user_id": user.id}
    await update.message.reply_text(
        "Bem-vindo! Quer cadastrar seu salario agora?",
        reply_markup=build_yes_no_keyboard(),
    )
    return State.ONBOARDING_SALARY_CHOICE


async def choose_onboarding_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == ONBOARDING_YES:
        context.user_data["guided"]["onboarding_step"] = "salary"
        await query.edit_message_text("Qual o valor do seu salario? Exemplo: 3500")
        return State.SALARY_AMOUNT
    if query.data == ONBOARDING_NO:
        await query.edit_message_text("Tudo bem. Voce pode cadastrar depois com /salario.")
        await query.message.reply_text(
            "Voce possui Ticket Alimentacao ou Ticket Refeicao?",
            reply_markup=build_yes_no_keyboard(),
        )
        return State.ONBOARDING_TICKET_CHOICE
    await query.edit_message_text("Opcao invalida. Envie /start para recomecar.")
    context.user_data.pop("guided", None)
    return ConversationHandler.END


async def choose_onboarding_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == ONBOARDING_NO:
        await _finish_onboarding(query.message, context)
        await query.edit_message_text("Tudo bem. Voce pode cadastrar tickets depois reiniciando o setup.")
        return ConversationHandler.END
    if query.data == ONBOARDING_YES:
        await query.edit_message_text(
            "Voce tem 1 beneficio ou os 2?",
            reply_markup=build_ticket_count_keyboard(),
        )
        return State.ONBOARDING_TICKET_COUNT
    await query.edit_message_text("Opcao invalida. Envie /start para recomecar.")
    context.user_data.pop("guided", None)
    return ConversationHandler.END


async def choose_onboarding_ticket_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    guided = context.user_data["guided"]
    if query.data == ONBOARDING_TWO_TICKETS:
        guided["ticket_types"] = [BENEFIT_ALIMENTACAO, BENEFIT_REFEICAO]
        guided["ticket_index"] = 0
        await query.edit_message_text("Qual o valor do Ticket Alimentacao? Exemplo: 700")
        return State.ONBOARDING_TICKET_AMOUNT
    if query.data == ONBOARDING_ONE_TICKET:
        await query.edit_message_text(
            "Qual beneficio voce possui?",
            reply_markup=build_ticket_type_keyboard(),
        )
        return State.ONBOARDING_TICKET_TYPE
    await query.edit_message_text("Opcao invalida. Envie /start para recomecar.")
    context.user_data.pop("guided", None)
    return ConversationHandler.END


async def choose_onboarding_ticket_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    guided = context.user_data["guided"]
    if query.data == ONBOARDING_TICKET_FOOD:
        guided["ticket_types"] = [BENEFIT_ALIMENTACAO]
        guided["ticket_index"] = 0
        await query.edit_message_text("Qual o valor do Ticket Alimentacao? Exemplo: 700")
        return State.ONBOARDING_TICKET_AMOUNT
    if query.data == ONBOARDING_TICKET_MEAL:
        guided["ticket_types"] = [BENEFIT_REFEICAO]
        guided["ticket_index"] = 0
        await query.edit_message_text("Qual o valor do Ticket Refeicao? Exemplo: 700")
        return State.ONBOARDING_TICKET_AMOUNT
    await query.edit_message_text("Opcao invalida. Envie /start para recomecar.")
    context.user_data.pop("guided", None)
    return ConversationHandler.END


async def receive_onboarding_ticket_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = parse_amount(update.message.text.strip(), command="/start")
    except ExpenseValidationError as exc:
        await update.message.reply_text(f"{exc}\n\nDigite o valor novamente ou use /cancelar.")
        return State.ONBOARDING_TICKET_AMOUNT

    guided = context.user_data["guided"]
    ticket_types = guided["ticket_types"]
    ticket_index = guided["ticket_index"]
    benefit_type = ticket_types[ticket_index]
    guided.setdefault("ticket_amounts", {})[benefit_type] = amount
    ticket_index += 1
    guided["ticket_index"] = ticket_index
    if ticket_index < len(ticket_types):
        await update.message.reply_text("Qual o valor do Ticket Refeicao? Exemplo: 700")
        return State.ONBOARDING_TICKET_AMOUNT

    with SessionLocal() as db:
        ticket_service = TicketService(TicketBenefitRepository(db), SalaryConfigRepository(db))
        for item_type, item_amount in guided["ticket_amounts"].items():
            ticket_service.configure_benefit(guided["user_id"], item_type, item_amount)

    await _finish_onboarding(update.message, context)
    return ConversationHandler.END


async def _finish_onboarding(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.user_data.pop("guided", {})
    user_id = data.get("user_id")
    if user_id:
        with SessionLocal() as db:
            UserRepository(db).mark_onboarding_completed(user_id)
    await message.reply_text(
        "Setup concluido. Voce ja pode usar o bot.",
        reply_markup=build_main_reply_keyboard(),
    )


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
    return await _ask_payment_source(update, context)


async def _send_expense_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.user_data["guided"]
    description = data.get("description") or "sem descricao"
    message = update.message if hasattr(update, "message") else update
    await message.reply_text(
        "\n".join(
            [
                "Confirmar gasto?",
                "",
                f"Valor: {format_currency(float(data['amount']))}",
                f"Categoria: {data['category']}",
                f"Descricao: {description}",
                f"Pagamento: {_payment_source_label(data.get('payment_source', PAYMENT_MONEY))}",
            ]
        ),
        reply_markup=build_expense_confirmation_keyboard(),
    )


async def _ask_payment_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    guided = context.user_data["guided"]
    with SessionLocal() as db:
        payment_sources = TicketService(
            TicketBenefitRepository(db),
            SalaryConfigRepository(db),
        ).active_payment_sources(guided["user_id"])
    if not payment_sources:
        guided["payment_source"] = PAYMENT_MONEY
        await _send_expense_confirmation(update, context)
        return State.ADD_CONFIRM
    await update.message.reply_text(
        "Qual a origem do pagamento?",
        reply_markup=build_payment_source_keyboard(payment_sources),
    )
    return State.ADD_PAYMENT_SOURCE


async def choose_payment_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    mapping = {
        PAYMENT_MONEY_CALLBACK: PAYMENT_MONEY,
        PAYMENT_TICKET_FOOD_CALLBACK: PAYMENT_TICKET_ALIMENTACAO,
        PAYMENT_TICKET_MEAL_CALLBACK: PAYMENT_TICKET_REFEICAO,
    }
    payment_source = mapping.get(query.data)
    if not payment_source:
        await query.edit_message_text("Origem de pagamento invalida. Digite /add para iniciar novamente.")
        context.user_data.pop("guided", None)
        return ConversationHandler.END
    context.user_data["guided"]["payment_source"] = payment_source
    await query.edit_message_text(f"Pagamento escolhido: {_payment_source_label(payment_source)}")
    await _send_expense_confirmation(query.message, context)
    return State.ADD_CONFIRM


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
        ticket_service = TicketService(TicketBenefitRepository(db), SalaryConfigRepository(db))
        try:
            expense = ExpenseService(repository, ticket_service).add_expense(
                data["user_id"],
                parsed,
                payment_source=data.get("payment_source", PAYMENT_MONEY),
            )
        except TicketBalanceError as exc:
            await query.edit_message_text(str(exc))
            return ConversationHandler.END
        summary = ReportService(repository, SalaryConfigRepository(db)).get_current_month_summary(data["user_id"])

    await query.edit_message_text(
        f"{format_expense_saved(expense, 'registrado')}\n"
        f"Total gasto no mes: {format_currency(float(summary['total']))}."
    )
    await _send_recurring_expense_suggestion(query.message, data["user_id"], expense)
    return ConversationHandler.END


async def skip_add_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["guided"]["description"] = None
    return await _ask_payment_source(update, context)


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


async def start_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        from app.bot.handlers import set_salary

        await set_salary(update, context)
        return ConversationHandler.END

    user = await _get_or_register_user(update)
    if not user:
        return ConversationHandler.END

    context.user_data["guided"] = {"type": "salary", "user_id": user.id}
    await update.message.reply_text("Qual o valor do seu salario? Exemplo: 3500\n\nUse /cancelar para cancelar.")
    return State.SALARY_AMOUNT


async def receive_salary_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = parse_amount(update.message.text.strip(), command="/salario")
    except ExpenseValidationError as exc:
        await update.message.reply_text(f"{exc}\n\nDigite o valor novamente ou use /cancelar.")
        return State.SALARY_AMOUNT

    context.user_data["guided"]["amount"] = amount
    await update.message.reply_text(
        "Como voce costuma receber?\n"
        "Digite 1 para dia fixo do mes.\n"
        "Digite 2 para 5o dia util."
    )
    return State.SALARY_SCHEDULE


async def receive_salary_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_value = update.message.text.strip().lower()
    if raw_value in {"2", "5", "5o", "quinto", "quinto dia util"}:
        context.user_data["guided"]["schedule_type"] = SCHEDULE_FIFTH_BUSINESS_DAY
        context.user_data["guided"]["pay_day"] = None
        return await _save_guided_salary(update, context)

    if raw_value in {"1", "dia", "dia fixo", "fixo"}:
        context.user_data["guided"]["schedule_type"] = SCHEDULE_FIXED_DAY
        await update.message.reply_text("Qual dia do mes? Exemplo: 25")
        return State.SALARY_PAY_DAY

    await update.message.reply_text("Digite 1 para dia fixo ou 2 para 5o dia util.")
    return State.SALARY_SCHEDULE


async def receive_salary_pay_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        pay_day = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Digite um dia valido entre 1 e 31.")
        return State.SALARY_PAY_DAY

    if pay_day < 1 or pay_day > 31:
        await update.message.reply_text("Digite um dia valido entre 1 e 31.")
        return State.SALARY_PAY_DAY

    context.user_data["guided"]["pay_day"] = pay_day
    return await _save_guided_salary(update, context)


async def _save_guided_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data["guided"]
    parsed_salary = ParsedSalary(
        amount=data["amount"],
        schedule_type=data["schedule_type"],
        pay_day=data.get("pay_day"),
    )

    with SessionLocal() as db:
        salary_config, _income = SalaryService(
            SalaryConfigRepository(db),
            IncomeRepository(db),
        ).configure_salary(data["user_id"], parsed_salary)

    if data.get("type") == "onboarding":
        data.pop("amount", None)
        data.pop("schedule_type", None)
        data.pop("pay_day", None)
        await update.message.reply_text(
            format_salary_saved(
                salary_config.amount,
                schedule_label(salary_config.schedule_type, salary_config.pay_day),
            )
        )
        await update.message.reply_text(
            "Voce possui Ticket Alimentacao ou Ticket Refeicao?",
            reply_markup=build_yes_no_keyboard(),
        )
        return State.ONBOARDING_TICKET_CHOICE

    context.user_data.pop("guided", None)
    await update.message.reply_text(
        format_salary_saved(
            salary_config.amount,
            schedule_label(salary_config.schedule_type, salary_config.pay_day),
        ),
        reply_markup=build_main_reply_keyboard(),
    )
    return ConversationHandler.END


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
        budget_service = BudgetService(BudgetRepository(db), ExpenseRepository(db), SalaryConfigRepository(db))
        budget_service.set_budget(data["user_id"], parsed)
        status = budget_service.get_budget_status(data["user_id"])

    await update.message.reply_text(format_budget_saved(status))
    return ConversationHandler.END


def _payment_source_label(payment_source: str) -> str:
    if payment_source == PAYMENT_TICKET_ALIMENTACAO:
        return "Ticket Alimentacao"
    if payment_source == PAYMENT_TICKET_REFEICAO:
        return "Ticket Refeicao"
    return "Dinheiro"


def build_conversation_handlers() -> list[ConversationHandler]:
    text_filter = filters.TEXT & ~filters.COMMAND
    return [
        ConversationHandler(
            entry_points=[CommandHandler("start", start_onboarding)],
            states={
                State.ONBOARDING_SALARY_CHOICE: [
                    CallbackQueryHandler(choose_onboarding_salary, pattern=f"^({ONBOARDING_YES}|{ONBOARDING_NO})$")
                ],
                State.SALARY_AMOUNT: [MessageHandler(text_filter, receive_salary_amount)],
                State.SALARY_SCHEDULE: [MessageHandler(text_filter, receive_salary_schedule)],
                State.SALARY_PAY_DAY: [MessageHandler(text_filter, receive_salary_pay_day)],
                State.ONBOARDING_TICKET_CHOICE: [
                    CallbackQueryHandler(choose_onboarding_ticket, pattern=f"^({ONBOARDING_YES}|{ONBOARDING_NO})$")
                ],
                State.ONBOARDING_TICKET_COUNT: [
                    CallbackQueryHandler(
                        choose_onboarding_ticket_count,
                        pattern=f"^({ONBOARDING_ONE_TICKET}|{ONBOARDING_TWO_TICKETS})$",
                    )
                ],
                State.ONBOARDING_TICKET_TYPE: [
                    CallbackQueryHandler(
                        choose_onboarding_ticket_type,
                        pattern=f"^({ONBOARDING_TICKET_FOOD}|{ONBOARDING_TICKET_MEAL})$",
                    )
                ],
                State.ONBOARDING_TICKET_AMOUNT: [MessageHandler(text_filter, receive_onboarding_ticket_amount)],
            },
            fallbacks=[CommandHandler("cancelar", cancel_conversation)],
        ),
        ConversationHandler(
            entry_points=[
                CommandHandler("add", start_add_expense),
                MessageHandler(filters.Regex(f"^{MAIN_BUTTON_ADD_EXPENSE}$"), start_add_expense),
            ],
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
                State.ADD_PAYMENT_SOURCE: [
                    CallbackQueryHandler(choose_payment_source, pattern=f"^{PAYMENT_PREFIX}:")
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
            entry_points=[
                CommandHandler("salario", start_salary),
                MessageHandler(filters.Regex(f"^{MAIN_BUTTON_SALARY}$"), start_salary),
            ],
            states={
                State.SALARY_AMOUNT: [MessageHandler(text_filter, receive_salary_amount)],
                State.SALARY_SCHEDULE: [MessageHandler(text_filter, receive_salary_schedule)],
                State.SALARY_PAY_DAY: [MessageHandler(text_filter, receive_salary_pay_day)],
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

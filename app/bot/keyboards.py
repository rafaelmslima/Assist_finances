from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


CATEGORY_PAGE_SIZE = 8
CATEGORY_PREFIX = "addcat"
CONFIRM_PREFIX = "addconfirm"
TUTORIAL_PREFIX = "tutorial"
CHART_PREFIX = "chart"
NEW_CATEGORY_CALLBACK = f"{CATEGORY_PREFIX}:new"
OTHER_CATEGORY_CALLBACK = f"{CATEGORY_PREFIX}:other"
CONFIRM_EXPENSE_CALLBACK = f"{CONFIRM_PREFIX}:yes"
CANCEL_EXPENSE_CALLBACK = f"{CONFIRM_PREFIX}:no"
TUTORIAL_BACK_CALLBACK = f"{TUTORIAL_PREFIX}:back"
TUTORIAL_EXIT_CALLBACK = f"{TUTORIAL_PREFIX}:exit"
CHART_BACK_CALLBACK = f"{CHART_PREFIX}:back"
CHART_CLOSE_CALLBACK = f"{CHART_PREFIX}:close"

TUTORIAL_TOPICS = [
    ("➕ Registrar gasto", "expense"),
    ("💰 Receitas e resumo", "income_balance"),
    ("🧠 Inteligencia financeira", "financial_intelligence"),
    ("📊 Resumo do mês", "month_summary"),
    ("📅 Gastos por dia", "day_summary"),
    ("📌 Gastos fixos", "fixed_expenses"),
    ("🎯 Orçamentos", "budgets"),
    ("📈 Previsão de gastos", "forecast"),
    ("🖼️ Gráficos", "charts"),
    ("✏️ Editar ou apagar lançamentos", "edit_delete"),
]

CHART_OPTIONS = [
    ("📊 Por categoria", "category"),
    ("📅 Evolução diária", "daily"),
    ("🏆 Top gastos", "top"),
    ("📈 Comparar meses", "compare"),
    ("🎯 Orçamento x gasto", "budget"),
    ("📌 Fixos x variáveis", "fixed_variable"),
]


def build_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["/add", "/hoje"],
            ["/mes", "/grafico"],
            ["/insights", "/disponivel"],
            ["/help"],
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
    )


def build_expense_category_keyboard(categories: list[str], page: int = 0) -> InlineKeyboardMarkup:
    unique_categories = sorted(dict.fromkeys(category for category in categories if category))
    total_pages = max(1, (len(unique_categories) + CATEGORY_PAGE_SIZE - 1) // CATEGORY_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * CATEGORY_PAGE_SIZE
    visible_categories = unique_categories[start:start + CATEGORY_PAGE_SIZE]

    rows = []
    for index in range(0, len(visible_categories), 2):
        row = []
        for offset, category in enumerate(visible_categories[index:index + 2]):
            category_index = start + index + offset
            row.append(
                InlineKeyboardButton(
                    _display_category(category),
                    callback_data=f"{CATEGORY_PREFIX}:select:{category_index}",
                )
            )
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton("Outros", callback_data=OTHER_CATEGORY_CALLBACK),
            InlineKeyboardButton("➕ Nova categoria", callback_data=NEW_CATEGORY_CALLBACK),
        ]
    )

    if total_pages > 1:
        navigation = []
        if page > 0:
            navigation.append(
                InlineKeyboardButton("⬅️ Anterior", callback_data=f"{CATEGORY_PREFIX}:page:{page - 1}")
            )
        if page < total_pages - 1:
            navigation.append(
                InlineKeyboardButton("➡️ Próxima", callback_data=f"{CATEGORY_PREFIX}:page:{page + 1}")
            )
        if navigation:
            rows.append(navigation)

    return InlineKeyboardMarkup(rows)


def build_expense_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data=CONFIRM_EXPENSE_CALLBACK),
                InlineKeyboardButton("❌ Cancelar", callback_data=CANCEL_EXPENSE_CALLBACK),
            ]
        ]
    )


def build_tutorial_menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for index in range(0, len(TUTORIAL_TOPICS), 2):
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"{TUTORIAL_PREFIX}:topic:{topic}")
                for label, topic in TUTORIAL_TOPICS[index:index + 2]
            ]
        )

    rows.append([InlineKeyboardButton("❌ Sair do tutorial", callback_data=TUTORIAL_EXIT_CALLBACK)])
    return InlineKeyboardMarkup(rows)


def build_tutorial_detail_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Voltar ao tutorial", callback_data=TUTORIAL_BACK_CALLBACK)],
            [InlineKeyboardButton("❌ Sair", callback_data=TUTORIAL_EXIT_CALLBACK)],
        ]
    )


def build_chart_menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for index in range(0, len(CHART_OPTIONS), 2):
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"{CHART_PREFIX}:show:{chart_type}")
                for label, chart_type in CHART_OPTIONS[index:index + 2]
            ]
        )
    rows.append([InlineKeyboardButton("❌ Cancelar", callback_data=CHART_CLOSE_CALLBACK)])
    return InlineKeyboardMarkup(rows)


def build_chart_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔙 Voltar aos gráficos", callback_data=CHART_BACK_CALLBACK),
                InlineKeyboardButton("❌ Fechar", callback_data=CHART_CLOSE_CALLBACK),
            ]
        ]
    )


def _display_category(category: str) -> str:
    return category[:1].upper() + category[1:]

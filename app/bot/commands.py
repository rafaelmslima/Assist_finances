from datetime import date

from app.database.models import Expense, FixedExpense, Income
from app.utils.money import to_money


START_TEXT = """
Ola! Eu sou seu bot de controle financeiro pessoal.

Comandos disponiveis:
/add - inicia cadastro guiado de gasto
/add valor categoria descricao opcional - registra um gasto rapido
/mes - mostra o resumo do mes atual
/hoje - lista os gastos de hoje
/dia 15 - lista os gastos de um dia do mes atual
/dia 22/04/2026 - lista os gastos de uma data especifica
/grafico - abre menu de graficos financeiros
/edit id valor categoria descricao opcional - edita um gasto
/delete id - apaga um gasto
/receita - inicia cadastro guiado de receita
/receita valor descricao opcional - registra uma entrada rapida
/disponivel - mostra quanto voce pode gastar por dia ate o fim do mes
/resumo - mostra um dashboard financeiro resumido
/orcamento - inicia cadastro guiado de orcamento
/orcamento valor ou /orcamento categoria valor - define orcamento rapido
/previsao - projeta gastos do mes
/comparar - compara com o mes anterior
/fixo - inicia cadastro guiado de gasto fixo
/fixo valor categoria descricao opcional - cadastra gasto fixo rapido
/fixos - lista gastos fixos
/delete_fixo id - apaga gasto fixo
/updates_off - desativa notificacoes de novidades
/updates_on - reativa notificacoes de novidades
/cancelar - cancela um fluxo guiado
/help - mostra ajuda e exemplos
""".strip()


HELP_TEXT = """
Voce pode usar os comandos de duas formas:

1. Rapido: envie o comando completo com os dados.
2. Guiado: envie apenas o comando e responda as perguntas do bot.

Use /cancelar para cancelar um fluxo guiado.
Use /pular para deixar uma descricao opcional em branco.

Adicionar gasto:
/add
/add valor categoria descricao opcional
Exemplos:
/add 25 mercado
/add 59.90 alimentacao almoco
/add 120 transporte uber

Resumo e consultas:
/mes - total do mes, total por categoria e quantidade de lancamentos
/hoje - lista os gastos de hoje
/dia 15 - lista os gastos do dia 15 do mes atual
/dia 22/04/2026 - lista os gastos dessa data
/grafico - abre menu com graficos por categoria, evolucao, top gastos e mais

Receitas e planejamento:
/receita
/receita valor descricao opcional
/receitas valor descricao opcional
/disponivel
/resumo
/orcamento
/orcamento valor
/orcamento categoria valor
/previsao
/comparar
/fixo
/fixo valor categoria descricao opcional
/fixos
/delete_fixo id
/updates_off
/updates_on

Editar e apagar:
/edit id valor categoria descricao opcional
/delete id

Exemplos:
/edit 3 42.50 mercado feira
/delete 3
/receita 3500 salario
/orcamento 3000
/orcamento alimentacao 900
/fixo 120 academia
/delete_fixo 2

Dicas:
- Use ponto ou virgula para centavos: 59.90 ou 59,90
- O id aparece nas listagens de /hoje e /dia
- Cada usuario ve apenas os proprios gastos
- Use /updates_off para parar novidades do bot e /updates_on para reativar
- Digite apenas /add, /receita, /fixo ou /orcamento para usar o modo guiado
""".strip()


def format_broadcast_result(total_users: int, sent_count: int, failed_count: int) -> str:
    return "\n".join(
        [
            "Broadcast concluido.",
            "",
            f"Usuarios encontrados: {total_users}",
            f"Enviados com sucesso: {sent_count}",
            f"Falhas: {failed_count}",
        ]
    )


def format_currency(value: object) -> str:
    return f"R$ {to_money(value):.2f}".replace(".", ",")


def format_month_summary(summary: dict[str, object]) -> str:
    total = float(summary["total"])
    categories = summary["categories"]
    count = int(summary["count"])
    month = int(summary["month"])
    year = int(summary["year"])

    if not categories:
        return f"Voce ainda nao registrou gastos em {month:02d}/{year}."

    lines = [
        f"Resumo de {month:02d}/{year}",
        f"Total gasto: {format_currency(total)}",
        f"Lancamentos: {count}",
        "",
        "Por categoria:",
    ]

    for category, category_total in categories.items():
        lines.append(f"- {category}: {format_currency(float(category_total))}")

    return "\n".join(lines)


def format_day_summary(summary: dict[str, object]) -> str:
    target_date = summary["date"]
    expenses = summary["expenses"]
    total = float(summary["total"])

    if not isinstance(target_date, date):
        raise TypeError("summary['date'] must be a date")

    if not expenses:
        return f"Nenhum gasto registrado em {target_date:%d/%m/%Y}."

    lines = [
        f"Gastos de {target_date:%d/%m/%Y}",
        f"Total do dia: {format_currency(total)}",
        "",
        "Lancamentos:",
    ]

    for expense in expenses:
        if not isinstance(expense, Expense):
            continue
        description = f" - {expense.description}" if expense.description else ""
        lines.append(
            f"#{expense.id} - {format_currency(expense.amount)} - {expense.category}{description}"
        )

    return "\n".join(lines)


def format_expense_saved(expense: Expense, action: str) -> str:
    description = f" ({expense.description})" if expense.description else ""
    return (
        f"Gasto {action}: #{expense.id} - "
        f"{format_currency(expense.amount)} em {expense.category}{description}."
    )


def format_income_saved(income: Income) -> str:
    description = f" ({income.description})" if income.description else ""
    return f"Receita registrada: #{income.id} - {format_currency(income.amount)}{description}."


def format_budget_saved(budget_status: dict[str, object]) -> str:
    lines = ["Orcamento atualizado."]
    total_budget = budget_status["total_budget"]
    total_used_percent = budget_status["total_used_percent"]
    if total_budget is not None:
        lines.append(f"Total: {format_currency(float(total_budget))}")
        lines.append(f"Usado no mes: {format_currency(float(budget_status['total_spent']))} ({total_used_percent}%)")

    categories = budget_status["categories"]
    if categories:
        lines.append("")
        lines.append("Por categoria:")
        for item in categories:
            lines.append(
                f"- {item['category']}: {format_currency(float(item['spent']))} de "
                f"{format_currency(float(item['budget']))} ({item['used_percent']}%)"
            )
    return "\n".join(lines)


def format_available_daily(available: dict[str, object]) -> str:
    return "\n".join(
        [
            "💰 Voce pode gastar por dia:",
            format_currency(float(available["daily_amount"])),
            "",
            "📊 Base:",
            f"Saldo restante: {format_currency(float(available['remaining_balance']))}",
            f"Dias restantes: {int(available['days_remaining'])}",
            "",
            f"⚠️ Tendencia: {available['trend']}",
        ]
    )


def format_smart_summary(summary: dict[str, object]) -> str:
    budget_percent = summary["budget_used_percent"]
    budget_line = (
        f"📊 Orcamento usado: {float(budget_percent):.1f}%".replace(".", ",")
        if budget_percent is not None
        else "📊 Orcamento usado: sem orcamento definido"
    )
    lines = [
        f"💸 Gasto do mes: {format_currency(float(summary['monthly_expenses']))}",
        f"💰 Saldo atual: {format_currency(float(summary['current_balance']))}",
        budget_line,
        f"📅 Media diaria: {format_currency(float(summary['current_daily_average']))}",
        f"📈 Tendencia: {summary['trend']}",
    ]

    alerts = summary["alerts"]
    if alerts:
        lines.append("")
        for alert in alerts:
            lines.append(f"⚠️ {alert}")

    return "\n".join(lines)


def format_forecast(forecast: dict[str, object], daily: bool = False) -> str:
    title = "Resumo diario" if daily else "Previsao do mes"
    lines = [
        title,
        "",
        f"Media diaria (ultimos 3 meses): {format_currency(float(forecast['historical_daily_average']))}",
        f"Gasto medio atual do mes: {format_currency(float(forecast['current_daily_average']))}",
        "",
        f"Projecao de gastos variaveis: {format_currency(float(forecast['projected_variable_expenses']))}",
        f"Gastos fixos: {format_currency(float(forecast['fixed_expenses']))}",
        f"Total previsto: {format_currency(float(forecast['total_forecast']))}",
        f"Tendencia: {forecast['trend']}",
    ]

    if forecast["total_budget"] is not None:
        difference = float(forecast["budget_difference"])
        label = "sobra" if difference >= 0 else "estouro"
        lines.append(f"Orcamento mensal: {format_currency(float(forecast['total_budget']))} ({label}: {format_currency(abs(difference))})")

    alerts = forecast["alerts"]
    if alerts:
        lines.append("")
        lines.append("Alertas:")
        for alert in alerts:
            lines.append(f"- {alert}")

    lines.append("")
    lines.append("Sugestao:")
    lines.append(str(forecast["suggestion"]))
    return "\n".join(lines)


def format_comparison(comparison: dict[str, object]) -> str:
    lines = [
        "Comparacao com mes anterior",
        f"Mes atual: {format_currency(float(comparison['current_total']))}",
        f"Mes anterior: {format_currency(float(comparison['previous_total']))}",
        f"Diferenca total: {_format_percent(comparison['total_percent'])}",
    ]

    categories = comparison["categories"]
    if categories:
        lines.append("")
        lines.append("Por categoria:")
        for category, item in categories.items():
            lines.append(
                f"- {category}: {format_currency(float(item['current']))} vs "
                f"{format_currency(float(item['previous']))} ({_format_percent(item['percent'])})"
            )
    return "\n".join(lines)


def format_fixed_expense_saved(fixed_expense: FixedExpense) -> str:
    description = f" ({fixed_expense.description})" if fixed_expense.description else ""
    return (
        f"Gasto fixo cadastrado: #{fixed_expense.id} - "
        f"{format_currency(fixed_expense.amount)} em {fixed_expense.category}{description}."
    )


def format_fixed_expenses(summary: dict[str, object]) -> str:
    fixed_expenses = summary["fixed_expenses"]
    if not fixed_expenses:
        return "Voce ainda nao cadastrou gastos fixos."

    lines = ["Gastos fixos previstos:"]
    for item in fixed_expenses:
        if not isinstance(item, FixedExpense):
            continue
        description = f" - {item.description}" if item.description else ""
        lines.append(f"#{item.id} - {format_currency(item.amount)} - {item.category}{description}")
    lines.append("")
    lines.append(f"Total dos fixos: {format_currency(float(summary['total']))}")
    return "\n".join(lines)


def _format_percent(value: object) -> str:
    if value is None:
        return "sem base anterior"
    sign = "+" if float(value) > 0 else ""
    return f"{sign}{float(value):.1f}%".replace(".", ",")

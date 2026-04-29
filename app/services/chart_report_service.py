from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from app.database.models import Expense
from app.database.repository import BudgetRepository, ExpenseRepository, FixedExpenseRepository
from app.services.budget_service import BudgetService
from app.services.date_service import elapsed_month_days, month_range, previous_month


BUDGET_EMPTY_MESSAGE = "\n".join(
    [
        "Voce ainda nao definiu um orcamento.",
        "",
        "Use:",
        "/orcamento 2500",
        "ou",
        "/orcamento alimentacao 600",
    ]
)


@dataclass(frozen=True)
class ChartReport:
    chart: BytesIO | None
    text: str


class ChartReportService:
    def __init__(
        self,
        expense_repository: ExpenseRepository,
        budget_repository: BudgetRepository,
        fixed_expense_repository: FixedExpenseRepository,
    ):
        self.expense_repository = expense_repository
        self.budget_repository = budget_repository
        self.fixed_expense_repository = fixed_expense_repository

    def build(self, user_id: int, chart_type: str) -> ChartReport:
        builders = {
            "category": self.category,
            "daily": self.daily_evolution,
            "top": self.top_expenses,
            "compare": self.month_comparison,
            "budget": self.budget_vs_spent,
            "fixed_variable": self.fixed_vs_variable,
        }
        builder = builders.get(chart_type)
        if not builder:
            return ChartReport(chart=None, text="Opcao de grafico invalida.")
        return builder(user_id)

    def category(self, user_id: int) -> ChartReport:
        start_date, end_date = month_range()
        categories = self.expense_repository.totals_by_category(user_id, start_date, end_date)
        if not categories:
            return ChartReport(chart=None, text="Voce ainda nao registrou gastos neste mes.")

        total = round(sum(categories.values()), 2)
        lines = [
            "Resumo por categoria",
            f"Total do mes: {format_currency(total)}",
            "",
            "Top 3 categorias:",
        ]
        for category, value in list(categories.items())[:3]:
            percent = (float(value) / total) * 100 if total else 0
            lines.append(f"- {category}: {format_currency(float(value))} ({percent:.1f}%)".replace(".", ","))

        return ChartReport(chart=build_category_chart(categories), text="\n".join(lines))

    def daily_evolution(self, user_id: int) -> ChartReport:
        today = date.today()
        start_date, end_date = month_range(today)
        expenses = self.expense_repository.list_by_period(user_id, start_date, end_date)
        if not expenses:
            return ChartReport(chart=None, text="Voce ainda nao registrou gastos neste mes.")

        daily_totals = {day: 0.0 for day in range(1, monthrange(today.year, today.month)[1] + 1)}
        for expense in expenses:
            daily_totals[expense.created_at.day] += float(expense.amount)

        total = round(sum(daily_totals.values()), 2)
        average = round(total / elapsed_month_days(today), 2)
        peak_day, peak_value = max(daily_totals.items(), key=lambda item: item[1])
        text = "\n".join(
            [
                "Evolucao diaria",
                f"Total do mes: {format_currency(total)}",
                f"Media diaria: {format_currency(average)}",
                f"Maior gasto: dia {peak_day:02d} com {format_currency(round(peak_value, 2))}",
            ]
        )
        return ChartReport(chart=build_daily_evolution_chart(daily_totals, average), text=text)

    def top_expenses(self, user_id: int) -> ChartReport:
        start_date, end_date = month_range()
        expenses = self.expense_repository.list_by_period(user_id, start_date, end_date)
        if not expenses:
            return ChartReport(chart=None, text="Voce ainda nao registrou gastos neste mes.")

        top_expenses = sorted(expenses, key=lambda expense: expense.amount, reverse=True)[:5]
        payload = [_expense_payload(expense) for expense in top_expenses]
        lines = ["Top gastos do mes"]
        for index, expense in enumerate(top_expenses, start=1):
            description = f" - {expense.description}" if expense.description else ""
            lines.append(
                f"{index}. {format_currency(float(expense.amount))} - {expense.category}{description}"
            )
        return ChartReport(chart=build_top_expenses_chart(payload), text="\n".join(lines))

    def month_comparison(self, user_id: int) -> ChartReport:
        current_start, current_end = month_range()
        previous_start, previous_end = month_range(previous_month())
        current_total = self.expense_repository.total_by_period(user_id, current_start, current_end)
        previous_total = self.expense_repository.total_by_period(user_id, previous_start, previous_end)
        if current_total <= 0 and previous_total <= 0:
            return ChartReport(
                chart=None,
                text="Ainda nao ha gastos suficientes no mes atual ou anterior para comparar.",
            )

        current_categories = self.expense_repository.totals_by_category(user_id, current_start, current_end)
        previous_categories = self.expense_repository.totals_by_category(user_id, previous_start, previous_end)
        categories = {}
        for category in sorted(set(current_categories) | set(previous_categories)):
            current_value = float(current_categories.get(category, 0))
            previous_value = float(previous_categories.get(category, 0))
            categories[category] = {
                "current": round(current_value, 2),
                "previous": round(previous_value, 2),
            }

        comparison = {
            "current_total": round(current_total, 2),
            "previous_total": round(previous_total, 2),
            "categories": categories,
        }
        text = "\n".join(
            [
                "Comparacao entre meses",
                f"Mes atual: {format_currency(round(current_total, 2))}",
                f"Mes anterior: {format_currency(round(previous_total, 2))}",
                f"Diferenca: {_format_change(current_total, previous_total)}",
            ]
        )
        return ChartReport(chart=build_month_comparison_chart(comparison), text=text)

    def budget_vs_spent(self, user_id: int) -> ChartReport:
        status = BudgetService(self.budget_repository, self.expense_repository).get_budget_status(user_id)
        categories = status["categories"]
        total_budget = status["total_budget"]
        if total_budget is None and not categories:
            return ChartReport(chart=None, text=BUDGET_EMPTY_MESSAGE)

        lines = ["Orcamento x gasto"]
        if total_budget is not None:
            lines.extend(
                [
                    f"Gasto atual: {format_currency(float(status['total_spent']))}",
                    f"Orcamento: {format_currency(float(total_budget))}",
                    f"Usado: {status['total_used_percent']}%",
                ]
            )

        over_budget = [
            item
            for item in categories
            if float(item["spent"]) > float(item["budget"])
        ]
        if over_budget:
            lines.append("")
            lines.append("Categorias acima do limite:")
            for item in over_budget:
                lines.append(
                    f"- {item['category']}: {format_currency(float(item['spent']))} de "
                    f"{format_currency(float(item['budget']))}"
                )
        else:
            lines.append("")
            lines.append("Nenhuma categoria acima do limite.")

        return ChartReport(chart=build_budget_chart(status), text="\n".join(lines))

    def fixed_vs_variable(self, user_id: int) -> ChartReport:
        fixed_expenses = self.fixed_expense_repository.list_by_user(user_id)
        if not fixed_expenses:
            return ChartReport(chart=None, text="Voce ainda nao cadastrou gastos fixos.")

        start_date, end_date = month_range()
        fixed_total = round(sum(float(item.amount) for item in fixed_expenses), 2)
        variable_total = round(self.expense_repository.total_by_period(user_id, start_date, end_date), 2)
        month_total = fixed_total + variable_total
        committed_percent = round((fixed_total / month_total) * 100, 1) if month_total else 0

        lines = [
            "Fixos x variaveis",
            f"Fixos previstos: {format_currency(fixed_total)}",
            f"Variaveis reais: {format_currency(variable_total)}",
            f"Percentual comprometido com fixos: {committed_percent}%",
        ]
        return ChartReport(
            chart=build_fixed_variable_chart(fixed_total, variable_total),
            text="\n".join(lines),
        )


def _expense_payload(expense: Expense) -> dict[str, object]:
    return {
        "amount": float(expense.amount),
        "category": expense.category,
        "description": expense.description,
    }


def format_currency(value: float) -> str:
    return f"R$ {value:.2f}".replace(".", ",")


def build_category_chart(category_totals: dict[str, float]) -> BytesIO:
    from app.utils.charts import build_category_chart as render

    return render(category_totals)


def build_daily_evolution_chart(daily_totals: dict[int, float], average: float) -> BytesIO:
    from app.utils.charts import build_daily_evolution_chart as render

    return render(daily_totals, average)


def build_top_expenses_chart(expenses: list[dict[str, object]]) -> BytesIO:
    from app.utils.charts import build_top_expenses_chart as render

    return render(expenses)


def build_month_comparison_chart(comparison: dict[str, object]) -> BytesIO:
    from app.utils.charts import build_month_comparison_chart as render

    return render(comparison)


def build_budget_chart(status: dict[str, object]) -> BytesIO:
    from app.utils.charts import build_budget_chart as render

    return render(status)


def build_fixed_variable_chart(fixed_total: float, variable_total: float) -> BytesIO:
    from app.utils.charts import build_fixed_variable_chart as render

    return render(fixed_total, variable_total)


def _format_change(current_value: float, previous_value: float) -> str:
    if previous_value == 0:
        return "sem base anterior" if current_value == 0 else "+100,0%"
    change = ((current_value - previous_value) / previous_value) * 100
    sign = "+" if change > 0 else ""
    return f"{sign}{change:.1f}%".replace(".", ",")

from datetime import date

from app.database.repository import BudgetRepository, ExpenseRepository, FixedExpenseRepository, IncomeRepository
from app.services.alert_service import AlertService
from app.services.date_service import days_in_month, elapsed_month_days, month_range, previous_month


class AnalyticsService:
    def __init__(
        self,
        expense_repository: ExpenseRepository,
        income_repository: IncomeRepository,
        budget_repository: BudgetRepository,
        fixed_expense_repository: FixedExpenseRepository,
        alert_service: AlertService | None = None,
    ):
        self.expense_repository = expense_repository
        self.income_repository = income_repository
        self.budget_repository = budget_repository
        self.fixed_expense_repository = fixed_expense_repository
        self.alert_service = alert_service or AlertService()

    def get_balance(self, telegram_user_id: int) -> dict[str, object]:
        start_date, end_date = month_range()
        monthly_income = self.income_repository.total_by_period(telegram_user_id, start_date, end_date)
        monthly_expenses = self.expense_repository.total_by_period(telegram_user_id, start_date, end_date)
        fixed_expenses = self.fixed_expense_repository.total_by_user(telegram_user_id)
        current_balance = round(monthly_income - monthly_expenses, 2)
        projected_balance = round(current_balance - fixed_expenses, 2)

        return {
            "current_balance": current_balance,
            "monthly_income": round(monthly_income, 2),
            "monthly_expenses": round(monthly_expenses, 2),
            "fixed_expenses": round(fixed_expenses, 2),
            "projected_balance": projected_balance,
        }

    def get_forecast(self, telegram_user_id: int, target_date: date | None = None) -> dict[str, object]:
        target_date = target_date or date.today()
        start_date, end_date = month_range(target_date)
        current_total = self.expense_repository.total_by_period(telegram_user_id, start_date, end_date)
        current_categories = self.expense_repository.totals_by_category(telegram_user_id, start_date, end_date)
        monthly_income = self.income_repository.total_by_period(telegram_user_id, start_date, end_date)
        fixed_expenses = self.fixed_expense_repository.total_by_user(telegram_user_id)
        total_budget = self.budget_repository.get_total_budget(telegram_user_id, target_date)
        category_budgets = self.budget_repository.get_category_budgets(telegram_user_id, target_date)

        historical_daily_average = self._historical_daily_average(telegram_user_id, target_date)
        current_daily_average = current_total / elapsed_month_days(target_date)
        projected_variable_expenses = current_daily_average * days_in_month(target_date)
        total_forecast = projected_variable_expenses + fixed_expenses
        projected_balance = monthly_income - total_forecast

        historical_category_averages = self._historical_category_daily_averages(
            telegram_user_id,
            target_date,
        )
        category_alerts = self._category_alerts(
            current_categories,
            category_budgets,
            historical_category_averages,
            target_date,
        )
        analysis = {
            "historical_daily_average": round(historical_daily_average, 2),
            "current_daily_average": round(current_daily_average, 2),
            "projected_variable_expenses": round(projected_variable_expenses, 2),
            "fixed_expenses": round(fixed_expenses, 2),
            "total_forecast": round(total_forecast, 2),
            "total_budget": float(total_budget.amount) if total_budget else None,
            "budget_difference": round((float(total_budget.amount) - total_forecast), 2) if total_budget else None,
            "monthly_income": round(monthly_income, 2),
            "projected_balance": round(projected_balance, 2),
            "trend": self._trend(historical_daily_average, current_daily_average),
            "category_alerts": category_alerts,
            "top_categories": [category for category, _ in sorted(current_categories.items(), key=lambda item: item[1], reverse=True)],
        }
        analysis["alerts"] = self.alert_service.build_alerts(analysis)
        analysis["suggestion"] = self.alert_service.build_suggestion(analysis)
        return analysis

    def compare_with_previous_month(self, telegram_user_id: int) -> dict[str, object]:
        current_start, current_end = month_range()
        previous_start, previous_end = month_range(previous_month())
        current_total = self.expense_repository.total_by_period(telegram_user_id, current_start, current_end)
        previous_total = self.expense_repository.total_by_period(telegram_user_id, previous_start, previous_end)
        current_categories = self.expense_repository.totals_by_category(telegram_user_id, current_start, current_end)
        previous_categories = self.expense_repository.totals_by_category(telegram_user_id, previous_start, previous_end)

        categories = {}
        for category in sorted(set(current_categories) | set(previous_categories)):
            current_value = float(current_categories.get(category, 0))
            previous_value = float(previous_categories.get(category, 0))
            categories[category] = {
                "current": round(current_value, 2),
                "previous": round(previous_value, 2),
                "percent": _change_percent(current_value, previous_value),
            }

        return {
            "current_total": round(current_total, 2),
            "previous_total": round(previous_total, 2),
            "total_percent": _change_percent(current_total, previous_total),
            "categories": categories,
        }

    def _historical_daily_average(self, telegram_user_id: int, target_date: date) -> float:
        totals = []
        cursor = previous_month(target_date)
        for _ in range(3):
            start_date, end_date = month_range(cursor)
            total = self.expense_repository.total_by_period(telegram_user_id, start_date, end_date)
            if total > 0:
                totals.append(total / days_in_month(cursor))
            cursor = previous_month(cursor)
        if not totals:
            start_date, end_date = month_range(target_date)
            total = self.expense_repository.total_by_period(telegram_user_id, start_date, end_date)
            return total / elapsed_month_days(target_date) if total > 0 else 0
        return sum(totals) / len(totals)

    def _historical_category_daily_averages(
        self,
        telegram_user_id: int,
        target_date: date,
    ) -> dict[str, float]:
        category_totals: dict[str, float] = {}
        months_with_data: dict[str, int] = {}
        cursor = previous_month(target_date)

        for _ in range(3):
            start_date, end_date = month_range(cursor)
            categories = self.expense_repository.totals_by_category(
                telegram_user_id,
                start_date,
                end_date,
            )
            for category, total in categories.items():
                category_totals[category] = category_totals.get(category, 0) + (total / days_in_month(cursor))
                months_with_data[category] = months_with_data.get(category, 0) + 1
            cursor = previous_month(cursor)

        return {
            category: total / months_with_data[category]
            for category, total in category_totals.items()
            if months_with_data.get(category)
        }

    @staticmethod
    def _trend(historical_daily_average: float, current_daily_average: float) -> str:
        if historical_daily_average <= 0 and current_daily_average <= 0:
            return "sem dados suficientes"
        if historical_daily_average <= 0:
            return "primeiros dados do usuario"
        ratio = current_daily_average / historical_daily_average
        if ratio >= 1.2:
            return "acima do padrao historico"
        if ratio <= 0.8:
            return "abaixo do padrao historico"
        return "dentro do padrao historico"

    @staticmethod
    def _category_alerts(
        current_categories: dict[str, float],
        category_budgets: dict[str, float],
        historical_category_averages: dict[str, float],
        target_date: date,
    ) -> list[str]:
        alerts = []
        for category, budget in category_budgets.items():
            spent = current_categories.get(category, 0)
            if budget > 0 and spent >= budget * 0.9:
                alerts.append(f"A categoria {category} ja usou {round((spent / budget) * 100, 1)}% do orcamento.")

        elapsed_days = elapsed_month_days(target_date)
        for category, spent in current_categories.items():
            historical_average = historical_category_averages.get(category, 0)
            if historical_average <= 0:
                continue
            current_average = spent / elapsed_days
            if current_average >= historical_average * 1.2:
                alerts.append(f"A categoria {category} esta pelo menos 20% acima do padrao historico.")
        return alerts


def _change_percent(current_value: float, previous_value: float) -> float | None:
    if previous_value == 0:
        return None if current_value == 0 else 100.0
    return round(((current_value - previous_value) / previous_value) * 100, 1)

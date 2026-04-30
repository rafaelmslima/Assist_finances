from datetime import date, datetime, time
from decimal import Decimal

from app.database.repository import BudgetRepository, ExpenseRepository, FixedExpenseRepository, IncomeRepository
from app.services.alert_service import AlertService
from app.services.date_service import (
    days_in_month,
    elapsed_month_days,
    month_range,
    previous_month,
    remaining_month_days,
)
from app.utils.money import ZERO, to_money


TREND_HIGH_RATIO = Decimal("1.20")
TREND_LOW_RATIO = Decimal("0.80")
CATEGORY_BUDGET_WARNING_RATIO = Decimal("0.90")
CATEGORY_GROWTH_THRESHOLD = 20.0
WEEKEND_DAYS = {5, 6}
WEEKDAY_NAMES = {
    0: "segunda-feira",
    1: "terca-feira",
    2: "quarta-feira",
    3: "quinta-feira",
    4: "sexta-feira",
    5: "sabado",
    6: "domingo",
}


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
        current_budget_usage_percent = (
            round((float(current_total) / float(total_budget.amount)) * 100, 1)
            if total_budget and total_budget.amount > 0
            else None
        )

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
            "historical_daily_average": to_money(historical_daily_average),
            "current_daily_average": to_money(current_daily_average),
            "projected_variable_expenses": to_money(projected_variable_expenses),
            "fixed_expenses": to_money(fixed_expenses),
            "total_forecast": to_money(total_forecast),
            "total_budget": total_budget.amount if total_budget else None,
            "current_budget_usage_percent": current_budget_usage_percent,
            "budget_difference": to_money(total_budget.amount - total_forecast) if total_budget else None,
            "monthly_income": to_money(monthly_income),
            "projected_balance": to_money(projected_balance),
            "trend": self._trend(historical_daily_average, current_daily_average),
            "category_alerts": category_alerts,
            "top_categories": [category for category, _ in sorted(current_categories.items(), key=lambda item: item[1], reverse=True)],
        }
        analysis["alerts"] = self.alert_service.build_alerts(analysis)
        analysis["suggestion"] = self.alert_service.build_suggestion(analysis)
        return analysis

    def get_available_daily_amount(
        self,
        telegram_user_id: int,
        target_date: date | None = None,
    ) -> dict[str, object]:
        target_date = target_date or date.today()
        start_date, end_date = month_range(target_date)
        monthly_income = self.income_repository.total_by_period(telegram_user_id, start_date, end_date)
        monthly_expenses = self.expense_repository.total_by_period(telegram_user_id, start_date, end_date)
        fixed_expenses = self.fixed_expense_repository.total_by_user(telegram_user_id)
        days_remaining = remaining_month_days(target_date)
        historical_daily_average = self._historical_daily_average(telegram_user_id, target_date)
        current_daily_average = monthly_expenses / elapsed_month_days(target_date)
        daily_excess = max(current_daily_average - historical_daily_average, ZERO) if historical_daily_average > 0 else ZERO
        remaining_balance = monthly_income - monthly_expenses - fixed_expenses
        daily_amount = (remaining_balance / days_remaining) - daily_excess

        return {
            "daily_amount": to_money(daily_amount),
            "remaining_balance": to_money(remaining_balance),
            "days_remaining": days_remaining,
            "monthly_income": to_money(monthly_income),
            "monthly_expenses": to_money(monthly_expenses),
            "fixed_expenses": to_money(fixed_expenses),
            "historical_daily_average": to_money(historical_daily_average),
            "current_daily_average": to_money(current_daily_average),
            "trend": self._trend_label(historical_daily_average, current_daily_average),
        }

    def get_smart_summary(
        self,
        telegram_user_id: int,
        target_date: date | None = None,
    ) -> dict[str, object]:
        target_date = target_date or date.today()
        start_date, end_date = month_range(target_date)
        monthly_income = self.income_repository.total_by_period(telegram_user_id, start_date, end_date)
        monthly_expenses = self.expense_repository.total_by_period(telegram_user_id, start_date, end_date)
        fixed_expenses = self.fixed_expense_repository.total_by_user(telegram_user_id)
        total_budget = self.budget_repository.get_total_budget(telegram_user_id, target_date)
        current_balance = monthly_income - monthly_expenses
        projected_balance = current_balance - fixed_expenses
        historical_daily_average = self._historical_daily_average(telegram_user_id, target_date)
        current_daily_average = monthly_expenses / elapsed_month_days(target_date)
        budget_used_percent = (
            round((float(monthly_expenses) / float(total_budget.amount)) * 100, 1)
            if total_budget and total_budget.amount > 0
            else None
        )

        analysis = {
            "historical_daily_average": to_money(historical_daily_average),
            "current_daily_average": to_money(current_daily_average),
            "total_budget": total_budget.amount if total_budget else None,
            "current_budget_usage_percent": budget_used_percent,
            "total_forecast": to_money(
                (current_daily_average * days_in_month(target_date)) + fixed_expenses,
            ),
            "fixed_expenses": to_money(fixed_expenses),
            "monthly_income": to_money(monthly_income),
            "projected_balance": to_money(projected_balance),
            "category_alerts": [],
        }

        return {
            "monthly_expenses": to_money(monthly_expenses),
            "current_balance": to_money(current_balance),
            "budget_used_percent": budget_used_percent,
            "current_daily_average": to_money(current_daily_average),
            "trend": self._short_trend_label(historical_daily_average, current_daily_average),
            "alerts": self.alert_service.build_alerts(analysis),
        }

    def compare_with_previous_month(self, telegram_user_id: int) -> dict[str, object]:
        current_start, current_end = month_range()
        previous_start, previous_end = month_range(previous_month())
        current_total = self.expense_repository.total_by_period(telegram_user_id, current_start, current_end)
        previous_total = self.expense_repository.total_by_period(telegram_user_id, previous_start, previous_end)
        current_categories = self.expense_repository.totals_by_category(telegram_user_id, current_start, current_end)
        previous_categories = self.expense_repository.totals_by_category(telegram_user_id, previous_start, previous_end)

        categories = {}
        for category in sorted(set(current_categories) | set(previous_categories)):
            current_value = current_categories.get(category, ZERO)
            previous_value = previous_categories.get(category, ZERO)
            categories[category] = {
                "current": to_money(current_value),
                "previous": to_money(previous_value),
                "percent": _change_percent(current_value, previous_value),
            }

        return {
            "current_total": to_money(current_total),
            "previous_total": to_money(previous_total),
            "total_percent": _change_percent(current_total, previous_total),
            "categories": categories,
        }

    def get_spending_insights(
        self,
        telegram_user_id: int,
        target_date: date | None = None,
    ) -> dict[str, object]:
        target_date = target_date or date.today()
        current_start, current_end = month_range(target_date)
        previous_start, previous_end = month_range(previous_month(target_date))
        history_start = _months_ago(target_date, 6)

        historical_expenses = self.expense_repository.list_by_period(
            telegram_user_id,
            datetime.combine(history_start, time.min),
            current_end,
        )
        current_total = self.expense_repository.total_by_period(
            telegram_user_id,
            current_start,
            current_end,
        )
        current_daily_average = current_total / elapsed_month_days(target_date)
        historical_daily_average = self._historical_daily_average(telegram_user_id, target_date)

        current_categories = self.expense_repository.totals_by_category(
            telegram_user_id,
            current_start,
            current_end,
        )
        previous_categories = self.expense_repository.totals_by_category(
            telegram_user_id,
            previous_start,
            previous_end,
        )

        category_growth = []
        for category in sorted(set(current_categories) | set(previous_categories)):
            previous_value = previous_categories.get(category, ZERO)
            if previous_value <= 0:
                continue
            percent = _change_percent(
                current_categories.get(category, ZERO),
                previous_value,
            )
            if percent is not None and percent > CATEGORY_GROWTH_THRESHOLD:
                category_growth.append({"category": category, "percent": percent})

        category_growth.sort(key=lambda item: float(item["percent"]), reverse=True)

        return {
            "weekday_pattern": self._weekday_pattern(historical_expenses),
            "category_growth": category_growth,
            "trend": self._trend_label(historical_daily_average, current_daily_average),
        }

    def _historical_daily_average(self, telegram_user_id: int, target_date: date) -> Decimal:
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
            return total / elapsed_month_days(target_date) if total > 0 else ZERO
        return sum(totals, ZERO) / len(totals)

    def _historical_category_daily_averages(
        self,
        telegram_user_id: int,
        target_date: date,
    ) -> dict[str, Decimal]:
        category_totals: dict[str, Decimal] = {}
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
                category_totals[category] = category_totals.get(category, ZERO) + (total / days_in_month(cursor))
                months_with_data[category] = months_with_data.get(category, 0) + 1
            cursor = previous_month(cursor)

        return {
            category: total / months_with_data[category]
            for category, total in category_totals.items()
            if months_with_data.get(category)
        }

    @staticmethod
    def _trend(historical_daily_average: Decimal, current_daily_average: Decimal) -> str:
        if historical_daily_average <= 0 and current_daily_average <= 0:
            return "sem dados suficientes"
        if historical_daily_average <= 0:
            return "primeiros dados do usuario"
        ratio = current_daily_average / historical_daily_average
        if ratio >= TREND_HIGH_RATIO:
            return "acima do padrao historico"
        if ratio <= TREND_LOW_RATIO:
            return "abaixo do padrao historico"
        return "dentro do padrao historico"

    @classmethod
    def _trend_label(cls, historical_daily_average: Decimal, current_daily_average: Decimal) -> str:
        trend = cls._trend(historical_daily_average, current_daily_average)
        if trend == "acima do padrao historico":
            return "acima do normal"
        if trend == "abaixo do padrao historico":
            return "abaixo do normal"
        if trend == "dentro do padrao historico":
            return "normal"
        return trend

    @classmethod
    def _short_trend_label(cls, historical_daily_average: Decimal, current_daily_average: Decimal) -> str:
        trend = cls._trend_label(historical_daily_average, current_daily_average)
        if trend in {"acima do normal", "abaixo do normal"}:
            return trend.split(" do normal")[0]
        if trend == "primeiros dados do usuario":
            return "normal"
        if trend == "sem dados suficientes":
            return "normal"
        return trend

    @staticmethod
    def _category_alerts(
        current_categories: dict[str, Decimal],
        category_budgets: dict[str, Decimal],
        historical_category_averages: dict[str, Decimal],
        target_date: date,
    ) -> list[str]:
        alerts = []
        for category, budget in category_budgets.items():
            spent = current_categories.get(category, ZERO)
            if budget > 0 and spent >= budget * CATEGORY_BUDGET_WARNING_RATIO:
                alerts.append(f"A categoria {category} ja usou {round((spent / budget) * 100, 1)}% do orcamento.")

        elapsed_days = elapsed_month_days(target_date)
        for category, spent in current_categories.items():
            historical_average = historical_category_averages.get(category, ZERO)
            if historical_average <= 0:
                continue
            current_average = spent / elapsed_days
            if current_average >= historical_average * TREND_HIGH_RATIO:
                alerts.append(f"A categoria {category} esta pelo menos 20% acima do padrao historico.")
        return alerts

    @staticmethod
    def _weekday_pattern(expenses: list[object]) -> dict[str, object]:
        totals_by_date: dict[date, Decimal] = {}
        for expense in expenses:
            created_at = getattr(expense, "created_at", None)
            amount = getattr(expense, "amount", ZERO)
            if not isinstance(created_at, datetime):
                continue
            expense_date = created_at.date()
            totals_by_date[expense_date] = totals_by_date.get(expense_date, ZERO) + to_money(amount)

        totals_by_weekday: dict[int, Decimal] = {}
        counts_by_weekday: dict[int, int] = {}
        for expense_date, total in totals_by_date.items():
            weekday = expense_date.weekday()
            totals_by_weekday[weekday] = totals_by_weekday.get(weekday, ZERO) + total
            counts_by_weekday[weekday] = counts_by_weekday.get(weekday, 0) + 1

        averages = {
            weekday: totals_by_weekday[weekday] / counts_by_weekday[weekday]
            for weekday in totals_by_weekday
            if counts_by_weekday.get(weekday)
        }
        if not averages:
            return {"type": "insufficient_data", "top_day": None, "averages": {}}

        top_day = max(averages, key=lambda weekday: averages[weekday])
        weekend_averages = [average for weekday, average in averages.items() if weekday in WEEKEND_DAYS]
        weekday_averages = [average for weekday, average in averages.items() if weekday not in WEEKEND_DAYS]
        weekend_average = sum(weekend_averages, ZERO) / len(weekend_averages) if weekend_averages else ZERO
        weekday_average = sum(weekday_averages, ZERO) / len(weekday_averages) if weekday_averages else ZERO

        if weekend_average > weekday_average and top_day in WEEKEND_DAYS:
            pattern_type = "weekend"
        elif weekend_average < weekday_average and top_day not in WEEKEND_DAYS:
            pattern_type = "weekday"
        else:
            pattern_type = "day"

        return {
            "type": pattern_type,
            "top_day": WEEKDAY_NAMES[top_day],
            "averages": {WEEKDAY_NAMES[weekday]: to_money(average) for weekday, average in averages.items()},
        }


def _change_percent(current_value: Decimal, previous_value: Decimal) -> float | None:
    if previous_value == 0:
        return None if current_value == 0 else 100.0
    return float(round(((current_value - previous_value) / previous_value) * 100, 1))


def _months_ago(target_date: date, months: int) -> date:
    year = target_date.year
    month = target_date.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)

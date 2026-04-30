from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.database.repository import BudgetRepository, ExpenseRepository, FixedExpenseRepository, IncomeRepository, SalaryConfigRepository, TicketBenefitRepository
from app.services.alert_service import AlertService
from app.services.date_service import (
    days_in_month,
    elapsed_month_days,
    month_range,
    previous_month,
)
from app.services.financial_overview_service import FinancialOverviewService
from app.services.ticket_service import PAYMENT_MONEY, PAYMENT_TICKET_ALIMENTACAO, PAYMENT_TICKET_REFEICAO, TicketService
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
        salary_config_repository: SalaryConfigRepository | None = None,
        ticket_benefit_repository: TicketBenefitRepository | None = None,
        alert_service: AlertService | None = None,
    ):
        self.expense_repository = expense_repository
        self.income_repository = income_repository
        self.budget_repository = budget_repository
        self.fixed_expense_repository = fixed_expense_repository
        self.salary_config_repository = salary_config_repository
        self.ticket_benefit_repository = ticket_benefit_repository
        self.alert_service = alert_service or AlertService()

    def get_forecast(self, telegram_user_id: int, target_date: date | None = None) -> dict[str, object]:
        target_date = target_date or date.today()
        overview = self._overview(telegram_user_id, target_date)
        cycle = overview.cycle
        start_date, end_date = cycle.start_date, cycle.end_date
        current_total = overview.variable_expenses
        current_categories = self.expense_repository.totals_by_category(
            telegram_user_id,
            start_date,
            end_date,
            payment_sources=[PAYMENT_MONEY],
        )
        monthly_income = overview.income
        fixed_expenses = overview.fixed_expenses
        total_budget = self.budget_repository.get_total_budget(telegram_user_id, cycle.start_day)
        category_budgets = self.budget_repository.get_category_budgets(telegram_user_id, cycle.start_day)

        historical_daily_average = self._historical_daily_average(telegram_user_id, target_date)
        current_daily_average = current_total / cycle.elapsed_days(target_date)
        projected_variable_expenses = current_daily_average * cycle.total_days()
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
            "current_balance": overview.current_balance,
            "available_balance": overview.available_balance,
            "projected_balance": to_money(projected_balance),
            "ticket_summaries": self._ticket_summaries(telegram_user_id, start_date, end_date, target_date),
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
        overview = self._overview(telegram_user_id, target_date)
        cycle = overview.cycle
        monthly_income = overview.income
        monthly_expenses = overview.variable_expenses
        fixed_expenses = overview.fixed_expenses
        days_remaining = cycle.remaining_days(target_date)
        historical_daily_average = self._historical_daily_average(telegram_user_id, target_date)
        current_daily_average = monthly_expenses / cycle.elapsed_days(target_date)
        daily_excess = max(current_daily_average - historical_daily_average, ZERO) if historical_daily_average > 0 else ZERO
        remaining_balance = overview.available_balance
        daily_amount = (remaining_balance / days_remaining) - daily_excess

        return {
            "daily_amount": to_money(daily_amount),
            "remaining_balance": to_money(remaining_balance),
            "days_remaining": days_remaining,
            "monthly_income": to_money(monthly_income),
            "monthly_expenses": to_money(monthly_expenses),
            "fixed_expenses": to_money(fixed_expenses),
            "ticket_summaries": self._ticket_summaries(telegram_user_id, cycle.start_date, cycle.end_date, target_date),
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
        overview = self._overview(telegram_user_id, target_date)
        cycle = overview.cycle
        monthly_income = overview.income
        monthly_expenses = overview.variable_expenses
        fixed_expenses = overview.fixed_expenses
        total_budget = self.budget_repository.get_total_budget(telegram_user_id, cycle.start_day)
        current_balance = overview.current_balance
        available_balance = overview.available_balance
        projected_balance = available_balance
        historical_daily_average = self._historical_daily_average(telegram_user_id, target_date)
        current_daily_average = monthly_expenses / cycle.elapsed_days(target_date)
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
                (current_daily_average * cycle.total_days()) + fixed_expenses,
            ),
            "fixed_expenses": to_money(fixed_expenses),
            "monthly_income": to_money(monthly_income),
            "projected_balance": to_money(projected_balance),
            "category_alerts": [],
        }

        return {
            "monthly_expenses": to_money(monthly_expenses),
            "current_balance": to_money(current_balance),
            "available_balance": to_money(available_balance),
            "fixed_expenses": to_money(fixed_expenses),
            "ticket_summaries": self._ticket_summaries(telegram_user_id, cycle.start_date, cycle.end_date, target_date),
            "budget_used_percent": budget_used_percent,
            "current_daily_average": to_money(current_daily_average),
            "trend": self._short_trend_label(historical_daily_average, current_daily_average),
            "alerts": self.alert_service.build_alerts(analysis),
        }

    def compare_with_previous_month(self, telegram_user_id: int) -> dict[str, object]:
        current_cycle = self._current_cycle(telegram_user_id, date.today())
        previous_cycle = self._previous_cycle(telegram_user_id, date.today())
        current_start, current_end = current_cycle.start_date, current_cycle.end_date
        previous_start, previous_end = previous_cycle.start_date, previous_cycle.end_date
        current_total = self.expense_repository.total_by_period(
            telegram_user_id,
            current_start,
            current_end,
            payment_sources=[PAYMENT_MONEY],
        )
        previous_total = self.expense_repository.total_by_period(
            telegram_user_id,
            previous_start,
            previous_end,
            payment_sources=[PAYMENT_MONEY],
        )
        current_categories = self.expense_repository.totals_by_category(
            telegram_user_id,
            current_start,
            current_end,
            payment_sources=[PAYMENT_MONEY],
        )
        previous_categories = self.expense_repository.totals_by_category(
            telegram_user_id,
            previous_start,
            previous_end,
            payment_sources=[PAYMENT_MONEY],
        )

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
        current_cycle = self._current_cycle(telegram_user_id, target_date)
        previous_cycle = self._previous_cycle(telegram_user_id, target_date)
        current_start, current_end = current_cycle.start_date, current_cycle.end_date
        previous_start, previous_end = previous_cycle.start_date, previous_cycle.end_date
        history_start = _months_ago(target_date, 6)

        historical_expenses = self.expense_repository.list_by_period(
            telegram_user_id,
            datetime.combine(history_start, time.min),
            current_end,
            payment_sources=[PAYMENT_MONEY],
        )
        current_total = self.expense_repository.total_by_period(
            telegram_user_id,
            current_start,
            current_end,
            payment_sources=[PAYMENT_MONEY],
        )
        current_daily_average = current_total / current_cycle.elapsed_days(target_date)
        historical_daily_average = self._historical_daily_average(telegram_user_id, target_date)

        current_categories = self.expense_repository.totals_by_category(
            telegram_user_id,
            current_start,
            current_end,
            payment_sources=[PAYMENT_MONEY],
        )
        previous_categories = self.expense_repository.totals_by_category(
            telegram_user_id,
            previous_start,
            previous_end,
            payment_sources=[PAYMENT_MONEY],
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
        current_cycle = self._current_cycle(telegram_user_id, target_date)
        total = self.expense_repository.total_by_period(
            telegram_user_id,
            current_cycle.start_date,
            current_cycle.end_date,
            payment_sources=[PAYMENT_MONEY],
        )
        return total / current_cycle.elapsed_days(target_date) if total > 0 else ZERO

    def _current_cycle(self, telegram_user_id: int, target_date: date):
        return self._overview_service().current_cycle(telegram_user_id, target_date)

    def _previous_cycle(self, telegram_user_id: int, target_date: date):
        return self._overview_service().previous_cycle(telegram_user_id, target_date)

    def _overview(self, telegram_user_id: int, target_date: date):
        return self._overview_service().get_overview(telegram_user_id, target_date)

    def _overview_service(self) -> FinancialOverviewService:
        return FinancialOverviewService(
            self.expense_repository,
            self.income_repository,
            self.fixed_expense_repository,
            self.salary_config_repository,
        )

    def _ticket_summaries(self, telegram_user_id: int, start_date: datetime, end_date: datetime, target_date: date):
        if not self.ticket_benefit_repository:
            return []
        spent_by_payment_source = {
            PAYMENT_TICKET_ALIMENTACAO: self.expense_repository.total_by_period(
                telegram_user_id,
                start_date,
                end_date,
                payment_sources=[PAYMENT_TICKET_ALIMENTACAO],
            ),
            PAYMENT_TICKET_REFEICAO: self.expense_repository.total_by_period(
                telegram_user_id,
                start_date,
                end_date,
                payment_sources=[PAYMENT_TICKET_REFEICAO],
            ),
        }
        return TicketService(
            self.ticket_benefit_repository,
            self.salary_config_repository,
        ).summary_by_period(telegram_user_id, spent_by_payment_source, target_date)

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
                payment_sources=[PAYMENT_MONEY],
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

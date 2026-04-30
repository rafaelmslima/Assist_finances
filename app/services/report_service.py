from calendar import monthrange
from datetime import date, datetime, time, timedelta

from app.database.models import Expense
from app.database.repository import ExpenseRepository, SalaryConfigRepository
from app.services.financial_cycle_service import FinancialCycleService
from app.utils.money import ZERO, to_money


class ReportService:
    def __init__(self, repository: ExpenseRepository, salary_config_repository: SalaryConfigRepository | None = None):
        self.repository = repository
        self.salary_config_repository = salary_config_repository

    def get_current_month_summary(self, user_id: int) -> dict[str, object]:
        cycle = self._current_cycle(user_id)
        start_date, end_date = cycle.start_date, cycle.end_date
        totals_by_category = self.repository.totals_by_category(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )
        total = to_money(sum(totals_by_category.values(), ZERO))
        count = self.repository.count_by_period(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        return {
            "total": total,
            "categories": totals_by_category,
            "count": count,
            "month": start_date.month,
            "year": start_date.year,
            "cycle_start": cycle.start_day,
            "cycle_end": cycle.end_day,
            "is_salary_cycle": cycle.is_salary_cycle,
        }

    def get_day_summary(self, user_id: int, target_date: date) -> dict[str, object]:
        start_date, end_date = self._day_range(target_date)
        expenses = self.repository.list_by_period(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )
        total = to_money(sum((expense.amount for expense in expenses), ZERO))

        return {
            "date": target_date,
            "expenses": expenses,
            "total": total,
            "count": len(expenses),
        }

    @staticmethod
    def _current_month_range() -> tuple[datetime, datetime]:
        now = datetime.now()
        start_date = datetime(now.year, now.month, 1)
        last_day = monthrange(now.year, now.month)[1]
        end_of_month = date(now.year, now.month, last_day)
        end_date = datetime.combine(end_of_month + timedelta(days=1), time.min)
        return start_date, end_date

    def _current_cycle(self, user_id: int):
        if self.salary_config_repository:
            return FinancialCycleService(self.salary_config_repository).current_cycle(user_id)
        start_date, end_date = self._current_month_range()
        from app.services.financial_cycle_service import FinancialCycle
        return FinancialCycle(start_date=start_date, end_date=end_date, is_salary_cycle=False)

    @staticmethod
    def _day_range(target_date: date) -> tuple[datetime, datetime]:
        start_date = datetime.combine(target_date, time.min)
        end_date = start_date + timedelta(days=1)
        return start_date, end_date

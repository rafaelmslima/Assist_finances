from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.database.repository import ExpenseRepository, FixedExpenseRepository, IncomeRepository, SalaryConfigRepository
from app.services.financial_cycle_service import FinancialCycle, FinancialCycleService
from app.services.date_service import month_range
from app.services.ticket_service import PAYMENT_MONEY
from app.utils.money import to_money


@dataclass(frozen=True)
class FinancialOverview:
    cycle: FinancialCycle
    income: Decimal
    variable_expenses: Decimal
    fixed_expenses: Decimal

    @property
    def current_balance(self) -> Decimal:
        return to_money(self.income - self.variable_expenses)

    @property
    def available_balance(self) -> Decimal:
        return to_money(self.current_balance - self.fixed_expenses)


class FinancialOverviewService:
    def __init__(
        self,
        expense_repository: ExpenseRepository,
        income_repository: IncomeRepository,
        fixed_expense_repository: FixedExpenseRepository,
        salary_config_repository: SalaryConfigRepository | None = None,
    ):
        self.expense_repository = expense_repository
        self.income_repository = income_repository
        self.fixed_expense_repository = fixed_expense_repository
        self.salary_config_repository = salary_config_repository

    def get_overview(self, user_id: int, target_date: date | None = None) -> FinancialOverview:
        target_date = target_date or date.today()
        cycle = self.current_cycle(user_id, target_date)
        start_date, end_date = cycle.start_date, cycle.end_date
        return FinancialOverview(
            cycle=cycle,
            income=self.income_repository.total_by_period(user_id, start_date, end_date),
            variable_expenses=self.expense_repository.total_by_period(
                user_id,
                start_date,
                end_date,
                payment_sources=[PAYMENT_MONEY],
            ),
            fixed_expenses=self.fixed_expense_repository.total_by_user(user_id),
        )

    def current_cycle(self, user_id: int, target_date: date | None = None) -> FinancialCycle:
        target_date = target_date or date.today()
        if self.salary_config_repository:
            return FinancialCycleService(self.salary_config_repository).current_cycle(user_id, target_date)
        start_date, end_date = month_range(target_date)
        return FinancialCycle(start_date=start_date, end_date=end_date, is_salary_cycle=False)

    def previous_cycle(self, user_id: int, target_date: date | None = None) -> FinancialCycle:
        target_date = target_date or date.today()
        if self.salary_config_repository:
            return FinancialCycleService(self.salary_config_repository).previous_cycle(user_id, target_date)
        from app.services.date_service import previous_month

        previous_start, previous_end = month_range(previous_month(target_date))
        return FinancialCycle(start_date=previous_start, end_date=previous_end, is_salary_cycle=False)

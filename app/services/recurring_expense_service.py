from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from app.database.models import Expense, FixedExpense
from app.database.repository import ExpenseRepository, FixedExpenseRepository
from app.utils.money import to_money


LOOKBACK_MONTHS = 6
MIN_RECURRING_MONTHS = 2
AMOUNT_TOLERANCE_RATIO = Decimal("0.10")
AMOUNT_TOLERANCE_MINIMUM = Decimal("2.00")


@dataclass(frozen=True)
class RecurringExpenseSuggestion:
    expense_id: int
    amount: Decimal
    category: str
    description: str | None
    occurrences: int

    @property
    def label(self) -> str:
        return self.description or self.category


class RecurringExpenseService:
    def __init__(
        self,
        expense_repository: ExpenseRepository,
        fixed_expense_repository: FixedExpenseRepository,
    ):
        self.expense_repository = expense_repository
        self.fixed_expense_repository = fixed_expense_repository

    def detect_for_expense(self, user_id: int, expense: Expense) -> RecurringExpenseSuggestion | None:
        if not isinstance(expense.created_at, datetime):
            return None

        if self.has_similar_fixed_expense(user_id, expense):
            return None

        start_date = _months_ago(expense.created_at.date(), LOOKBACK_MONTHS)
        history = self.expense_repository.list_by_period(
            user_id,
            datetime.combine(start_date, time.min),
            expense.created_at,
        )
        similar_months = {
            _month_key(item.created_at)
            for item in history
            if item.id != expense.id and self._is_similar_expense(expense, item)
        }
        similar_months.add(_month_key(expense.created_at))

        if len(similar_months) < MIN_RECURRING_MONTHS:
            return None

        return RecurringExpenseSuggestion(
            expense_id=expense.id,
            amount=to_money(expense.amount),
            category=expense.category,
            description=expense.description,
            occurrences=len(similar_months),
        )

    def has_similar_fixed_expense(self, user_id: int, expense: Expense) -> bool:
        return self._has_similar_fixed_expense(
            self.fixed_expense_repository.list_by_user(user_id),
            expense,
        )

    @staticmethod
    def _is_similar_expense(reference: Expense, candidate: Expense) -> bool:
        if reference.category != candidate.category:
            return False
        return _amounts_are_close(to_money(reference.amount), to_money(candidate.amount))

    @staticmethod
    def _has_similar_fixed_expense(fixed_expenses: list[FixedExpense], expense: Expense) -> bool:
        for fixed_expense in fixed_expenses:
            if fixed_expense.category != expense.category:
                continue
            if not _amounts_are_close(to_money(fixed_expense.amount), to_money(expense.amount)):
                continue
            if expense.description and fixed_expense.description:
                return expense.description.strip().lower() == fixed_expense.description.strip().lower()
            return True
        return False


def _amounts_are_close(first: Decimal, second: Decimal) -> bool:
    tolerance = max(first * AMOUNT_TOLERANCE_RATIO, AMOUNT_TOLERANCE_MINIMUM)
    return abs(first - second) <= tolerance


def _month_key(value: datetime) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _months_ago(target_date: date, months: int) -> date:
    year = target_date.year
    month = target_date.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)

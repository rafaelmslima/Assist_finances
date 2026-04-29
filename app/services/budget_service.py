from app.database.models import Budget
from app.database.repository import BudgetRepository, ExpenseRepository
from app.services.date_service import month_range
from app.utils.money import ZERO, to_money
from app.utils.validators import ParsedBudget


class BudgetService:
    def __init__(self, budget_repository: BudgetRepository, expense_repository: ExpenseRepository):
        self.budget_repository = budget_repository
        self.expense_repository = expense_repository

    def set_budget(self, user_id: int, parsed_budget: ParsedBudget) -> Budget:
        return self.budget_repository.upsert(
            user_id=user_id,
            amount=parsed_budget.amount,
            category=parsed_budget.category,
        )

    def get_budget_status(self, user_id: int) -> dict[str, object]:
        start_date, end_date = month_range()
        budgets = self.budget_repository.list_by_month(user_id)
        expenses_by_category = self.expense_repository.totals_by_category(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )
        total_spent = to_money(sum(expenses_by_category.values(), ZERO))

        total_budget = next((budget.amount for budget in budgets if budget.category is None), None)
        categories = []
        for budget in budgets:
            if budget.category is None:
                continue
            spent = to_money(expenses_by_category.get(budget.category))
            categories.append(
                {
                    "category": budget.category,
                    "budget": budget.amount,
                    "spent": spent,
                    "used_percent": _percentage(spent, budget.amount),
                }
            )

        return {
            "total_budget": total_budget if total_budget is not None else None,
            "total_spent": total_spent,
            "total_used_percent": _percentage(total_spent, total_budget) if total_budget else None,
            "categories": categories,
        }


def _percentage(value: object, base: object | None) -> float:
    if not base:
        return 0
    return round((float(value) / float(base)) * 100, 1)

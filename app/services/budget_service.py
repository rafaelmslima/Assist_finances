from app.database.models import Budget
from app.database.repository import BudgetRepository, ExpenseRepository
from app.services.date_service import month_range
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
        total_spent = sum(expenses_by_category.values())

        total_budget = next((budget.amount for budget in budgets if budget.category is None), None)
        categories = []
        for budget in budgets:
            if budget.category is None:
                continue
            spent = float(expenses_by_category.get(budget.category, 0))
            categories.append(
                {
                    "category": budget.category,
                    "budget": float(budget.amount),
                    "spent": round(spent, 2),
                    "used_percent": _percentage(spent, budget.amount),
                }
            )

        return {
            "total_budget": float(total_budget) if total_budget is not None else None,
            "total_spent": round(total_spent, 2),
            "total_used_percent": _percentage(total_spent, total_budget) if total_budget else None,
            "categories": categories,
        }


def _percentage(value: float, base: float | None) -> float:
    if not base:
        return 0
    return round((value / base) * 100, 1)

from app.database.models import FixedExpense
from app.database.repository import FixedExpenseRepository
from app.utils.validators import ParsedFixedExpense


class FixedExpenseService:
    def __init__(self, repository: FixedExpenseRepository):
        self.repository = repository

    def add_fixed_expense(
        self,
        user_id: int,
        parsed_fixed_expense: ParsedFixedExpense,
    ) -> FixedExpense:
        return self.repository.create(
            user_id=user_id,
            amount=parsed_fixed_expense.amount,
            category=parsed_fixed_expense.category,
            description=parsed_fixed_expense.description,
        )

    def list_fixed_expenses(self, user_id: int) -> dict[str, object]:
        fixed_expenses = self.repository.list_by_user(user_id)
        total = round(sum(item.amount for item in fixed_expenses), 2)
        return {"fixed_expenses": fixed_expenses, "total": total}

    def delete_fixed_expense(self, user_id: int, fixed_expense_id: int) -> bool:
        return self.repository.delete(user_id, fixed_expense_id)

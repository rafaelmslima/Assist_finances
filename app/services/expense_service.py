from app.database.models import Expense
from app.database.repository import ExpenseRepository
from app.utils.validators import ParsedExpense


class ExpenseService:
    def __init__(self, repository: ExpenseRepository):
        self.repository = repository

    def add_expense(self, user_id: int, parsed_expense: ParsedExpense) -> Expense:
        return self.repository.create(
            user_id=user_id,
            amount=parsed_expense.amount,
            category=parsed_expense.category,
            description=parsed_expense.description,
        )

    def edit_expense(
        self,
        user_id: int,
        expense_id: int,
        parsed_expense: ParsedExpense,
    ) -> Expense | None:
        return self.repository.update(
            user_id=user_id,
            expense_id=expense_id,
            amount=parsed_expense.amount,
            category=parsed_expense.category,
            description=parsed_expense.description,
        )

    def delete_expense(self, user_id: int, expense_id: int) -> bool:
        return self.repository.delete(user_id=user_id, expense_id=expense_id)

    def get_user_expense_categories(self, user_id: int) -> list[str]:
        return self.repository.list_distinct_categories(user_id)

from app.database.models import Expense
from app.database.repository import ExpenseRepository
from app.services.ticket_service import PAYMENT_MONEY, TicketService
from app.utils.validators import ParsedExpense


class ExpenseService:
    def __init__(self, repository: ExpenseRepository, ticket_service: TicketService | None = None):
        self.repository = repository
        self.ticket_service = ticket_service

    def add_expense(
        self,
        user_id: int,
        parsed_expense: ParsedExpense,
        payment_source: str = PAYMENT_MONEY,
    ) -> Expense:
        if self.ticket_service:
            self.ticket_service.debit(user_id, payment_source, parsed_expense.amount)
        return self.repository.create(
            user_id=user_id,
            amount=parsed_expense.amount,
            category=parsed_expense.category,
            description=parsed_expense.description,
            payment_source=payment_source,
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

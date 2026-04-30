from datetime import datetime

from app.database.models import Income
from app.database.repository import IncomeRepository
from app.utils.validators import ParsedIncome


class IncomeService:
    def __init__(self, repository: IncomeRepository):
        self.repository = repository

    def add_income(
        self,
        user_id: int,
        parsed_income: ParsedIncome,
        created_at: datetime | None = None,
    ) -> Income:
        return self.repository.create(
            user_id=user_id,
            amount=parsed_income.amount,
            description=parsed_income.description,
            created_at=created_at,
        )

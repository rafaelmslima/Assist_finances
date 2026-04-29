from datetime import date, datetime

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.database.models import Budget, DailyNotification, Expense, FixedExpense, Income, User


def _month_key(target: date | datetime) -> str:
    return f"{target.year:04d}-{target.month:02d}"


def _telegram_user_id_for_user_id(db: Session, user_id: int) -> int:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("Usuario interno nao encontrado.")
    return user.telegram_user_id


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_telegram_user_id(self, telegram_user_id: int) -> User | None:
        statement = select(User).where(User.telegram_user_id == telegram_user_id)
        return self.db.scalar(statement)

    def create(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        first_name: str | None,
        username: str | None,
    ) -> User:
        user = User(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            first_name=first_name,
            username=username,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_telegram_profile(
        self,
        user: User,
        telegram_chat_id: int,
        first_name: str | None,
        username: str | None,
    ) -> User:
        changed = False
        if user.telegram_chat_id != telegram_chat_id:
            user.telegram_chat_id = telegram_chat_id
            changed = True
        if user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if user.username != username:
            user.username = username
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True

        if changed:
            self.db.commit()
            self.db.refresh(user)
        return user

    def upsert_from_telegram(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        first_name: str | None,
        username: str | None,
    ) -> User:
        user = self.get_by_telegram_user_id(telegram_user_id)
        if not user:
            return self.create(
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                first_name=first_name,
                username=username,
            )
        return self.update_telegram_profile(user, telegram_chat_id, first_name, username)

    def list_active_users(self) -> list[User]:
        statement = select(User).where(User.is_active.is_(True)).order_by(User.id.asc())
        return list(self.db.scalars(statement).all())


class ExpenseRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: int,
        amount: float,
        category: str,
        description: str | None = None,
    ) -> Expense:
        expense = Expense(
            user_id=user_id,
            telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
            amount=amount,
            category=category,
            description=description,
        )
        self.db.add(expense)
        self.db.commit()
        self.db.refresh(expense)
        return expense

    def get_by_id(self, user_id: int, expense_id: int) -> Expense | None:
        statement = select(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == user_id,
        )
        return self.db.scalar(statement)

    def update(
        self,
        user_id: int,
        expense_id: int,
        amount: float,
        category: str,
        description: str | None,
    ) -> Expense | None:
        expense = self.get_by_id(user_id, expense_id)
        if not expense:
            return None

        expense.amount = amount
        expense.category = category
        expense.description = description
        self.db.commit()
        self.db.refresh(expense)
        return expense

    def delete(self, user_id: int, expense_id: int) -> bool:
        statement = delete(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == user_id,
        )
        result = self.db.execute(statement)
        self.db.commit()
        return bool(result.rowcount)

    def list_by_period(
        self,
        user_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Expense]:
        statement: Select[tuple[Expense]] = (
            select(Expense)
            .where(
                Expense.user_id == user_id,
                Expense.created_at >= start_date,
                Expense.created_at < end_date,
            )
            .order_by(Expense.created_at.asc(), Expense.id.asc())
        )
        return list(self.db.scalars(statement).all())

    def totals_by_category(
        self,
        user_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, float]:
        statement = (
            select(Expense.category, func.sum(Expense.amount))
            .where(
                Expense.user_id == user_id,
                Expense.created_at >= start_date,
                Expense.created_at < end_date,
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        )
        return {category: float(total or 0) for category, total in self.db.execute(statement)}

    def count_by_period(
        self,
        user_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        statement = select(func.count(Expense.id)).where(
            Expense.user_id == user_id,
            Expense.created_at >= start_date,
            Expense.created_at < end_date,
        )
        return int(self.db.scalar(statement) or 0)

    def total_by_period(
        self,
        user_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> float:
        statement = select(func.sum(Expense.amount)).where(
            Expense.user_id == user_id,
            Expense.created_at >= start_date,
            Expense.created_at < end_date,
        )
        return float(self.db.scalar(statement) or 0)


class IncomeRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: int,
        amount: float,
        description: str | None = None,
    ) -> Income:
        income = Income(
            user_id=user_id,
            telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
            amount=amount,
            description=description,
        )
        self.db.add(income)
        self.db.commit()
        self.db.refresh(income)
        return income

    def total_by_period(
        self,
        user_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> float:
        statement = select(func.sum(Income.amount)).where(
            Income.user_id == user_id,
            Income.created_at >= start_date,
            Income.created_at < end_date,
        )
        return float(self.db.scalar(statement) or 0)


class BudgetRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(
        self,
        user_id: int,
        amount: float,
        category: str | None,
        target_date: date | None = None,
    ) -> Budget:
        month = _month_key(target_date or date.today())
        statement = select(Budget).where(
            Budget.user_id == user_id,
            Budget.month == month,
            Budget.category.is_(None) if category is None else Budget.category == category,
        )
        budget = self.db.scalar(statement)
        if budget:
            budget.amount = amount
        else:
            budget = Budget(
                user_id=user_id,
                telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
                month=month,
                category=category,
                amount=amount,
            )
            self.db.add(budget)

        self.db.commit()
        self.db.refresh(budget)
        return budget

    def list_by_month(self, user_id: int, target_date: date | None = None) -> list[Budget]:
        month = _month_key(target_date or date.today())
        statement = (
            select(Budget)
            .where(Budget.user_id == user_id, Budget.month == month)
            .order_by(Budget.category.asc().nullsfirst())
        )
        return list(self.db.scalars(statement).all())

    def get_total_budget(self, user_id: int, target_date: date | None = None) -> Budget | None:
        month = _month_key(target_date or date.today())
        statement = select(Budget).where(
            Budget.user_id == user_id,
            Budget.month == month,
            Budget.category.is_(None),
        )
        return self.db.scalar(statement)

    def get_category_budgets(self, user_id: int, target_date: date | None = None) -> dict[str, float]:
        month = _month_key(target_date or date.today())
        statement = select(Budget.category, Budget.amount).where(
            Budget.user_id == user_id,
            Budget.month == month,
            Budget.category.is_not(None),
        )
        return {str(category): float(amount) for category, amount in self.db.execute(statement)}


class FixedExpenseRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: int,
        amount: float,
        category: str,
        description: str | None = None,
    ) -> FixedExpense:
        fixed_expense = FixedExpense(
            user_id=user_id,
            telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
            amount=amount,
            category=category,
            description=description,
        )
        self.db.add(fixed_expense)
        self.db.commit()
        self.db.refresh(fixed_expense)
        return fixed_expense

    def list_by_user(self, user_id: int) -> list[FixedExpense]:
        statement = (
            select(FixedExpense)
            .where(FixedExpense.user_id == user_id)
            .order_by(FixedExpense.category.asc(), FixedExpense.id.asc())
        )
        return list(self.db.scalars(statement).all())

    def total_by_user(self, user_id: int) -> float:
        statement = select(func.sum(FixedExpense.amount)).where(
            FixedExpense.user_id == user_id,
        )
        return float(self.db.scalar(statement) or 0)

    def delete(self, user_id: int, fixed_expense_id: int) -> bool:
        statement = delete(FixedExpense).where(
            FixedExpense.id == fixed_expense_id,
            FixedExpense.user_id == user_id,
        )
        result = self.db.execute(statement)
        self.db.commit()
        return bool(result.rowcount)


class DailyNotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def was_sent(self, user_id: int, sent_on: date) -> bool:
        statement = select(func.count(DailyNotification.id)).where(
            DailyNotification.user_id == user_id,
            DailyNotification.sent_on == sent_on,
        )
        return bool(self.db.scalar(statement))

    def mark_sent(self, user_id: int, sent_on: date) -> None:
        if self.was_sent(user_id, sent_on):
            return
        self.db.add(
            DailyNotification(
                user_id=user_id,
                telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
                sent_on=sent_on,
            )
        )
        self.db.commit()

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import Budget, DailyNotification, Expense, FixedExpense, Income, SalaryConfig, UpdateBroadcast, User
from app.utils.money import to_money


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

    def list_active_update_recipients(self) -> list[User]:
        statement = (
            select(User)
            .where(
                User.is_active.is_(True),
                User.telegram_chat_id.is_not(None),
                User.receive_updates_notifications.is_(True),
            )
            .order_by(User.id.asc())
        )
        return list(self.db.scalars(statement).all())

    def set_receive_updates_notifications(self, user_id: int, enabled: bool) -> User | None:
        user = self.db.get(User, user_id)
        if not user:
            return None
        user.receive_updates_notifications = enabled
        self.db.commit()
        self.db.refresh(user)
        return user


class UpdateBroadcastRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        admin_user_id: int,
        message: str,
        total_users: int,
        sent_count: int,
        failed_count: int,
    ) -> UpdateBroadcast:
        broadcast = UpdateBroadcast(
            admin_user_id=admin_user_id,
            message=message,
            total_users=total_users,
            sent_count=sent_count,
            failed_count=failed_count,
        )
        self.db.add(broadcast)
        self.db.commit()
        self.db.refresh(broadcast)
        return broadcast


class ExpenseRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: int,
        amount: Decimal | float | int | str,
        category: str,
        description: str | None = None,
    ) -> Expense:
        expense = Expense(
            user_id=user_id,
            telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
            amount=to_money(amount),
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
        amount: Decimal | float | int | str,
        category: str,
        description: str | None,
    ) -> Expense | None:
        expense = self.get_by_id(user_id, expense_id)
        if not expense:
            return None

        expense.amount = to_money(amount)
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
    ) -> dict[str, Decimal]:
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
        return {category: to_money(total) for category, total in self.db.execute(statement)}

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
    ) -> Decimal:
        statement = select(func.sum(Expense.amount)).where(
            Expense.user_id == user_id,
            Expense.created_at >= start_date,
            Expense.created_at < end_date,
        )
        return to_money(self.db.scalar(statement))

    def list_distinct_categories(self, user_id: int) -> list[str]:
        statement = (
            select(Expense.category)
            .where(Expense.user_id == user_id)
            .where(Expense.category.is_not(None))
            .distinct()
            .order_by(Expense.category.asc())
        )
        return [str(category) for category in self.db.scalars(statement).all() if category]


class IncomeRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: int,
        amount: Decimal | float | int | str,
        description: str | None = None,
        created_at: datetime | None = None,
    ) -> Income:
        income = Income(
            user_id=user_id,
            telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
            amount=to_money(amount),
            description=description,
        )
        if created_at is not None:
            income.created_at = created_at
        self.db.add(income)
        self.db.commit()
        self.db.refresh(income)
        return income

    def total_by_period(
        self,
        user_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> Decimal:
        statement = select(func.sum(Income.amount)).where(
            Income.user_id == user_id,
            Income.created_at >= start_date,
            Income.created_at < end_date,
        )
        return to_money(self.db.scalar(statement))


class SalaryConfigRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user(self, user_id: int) -> SalaryConfig | None:
        statement = select(SalaryConfig).where(SalaryConfig.user_id == user_id)
        return self.db.scalar(statement)

    def upsert(
        self,
        user_id: int,
        amount: Decimal | float | int | str,
        schedule_type: str,
        pay_day: int | None,
        current_cycle_start: date | None,
        is_active: bool = True,
    ) -> SalaryConfig:
        salary_config = self.get_by_user(user_id)
        if not salary_config:
            salary_config = SalaryConfig(
                user_id=user_id,
                telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
                amount=to_money(amount),
                schedule_type=schedule_type,
                pay_day=pay_day,
                is_active=is_active,
                current_cycle_start=current_cycle_start,
            )
            self.db.add(salary_config)
        else:
            salary_config.amount = to_money(amount)
            salary_config.schedule_type = schedule_type
            salary_config.pay_day = pay_day
            salary_config.is_active = is_active
            if current_cycle_start is not None:
                salary_config.current_cycle_start = current_cycle_start

        self.db.commit()
        self.db.refresh(salary_config)
        return salary_config

    def set_cycle_start(self, user_id: int, cycle_start: date) -> SalaryConfig | None:
        salary_config = self.get_by_user(user_id)
        if not salary_config:
            return None
        salary_config.current_cycle_start = cycle_start
        self.db.commit()
        self.db.refresh(salary_config)
        return salary_config

    def set_last_auto_salary_on(self, user_id: int, salary_on: date) -> SalaryConfig | None:
        salary_config = self.get_by_user(user_id)
        if not salary_config:
            return None
        salary_config.last_auto_salary_on = salary_on
        self.db.commit()
        self.db.refresh(salary_config)
        return salary_config

    def list_active(self) -> list[SalaryConfig]:
        statement = (
            select(SalaryConfig)
            .where(SalaryConfig.is_active.is_(True))
            .order_by(SalaryConfig.user_id.asc())
        )
        return list(self.db.scalars(statement).all())


class BudgetRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(
        self,
        user_id: int,
        amount: Decimal | float | int | str,
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
            budget.amount = to_money(amount)
        else:
            budget = Budget(
                user_id=user_id,
                telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
                month=month,
                category=category,
                amount=to_money(amount),
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

    def get_category_budgets(self, user_id: int, target_date: date | None = None) -> dict[str, Decimal]:
        month = _month_key(target_date or date.today())
        statement = select(Budget.category, Budget.amount).where(
            Budget.user_id == user_id,
            Budget.month == month,
            Budget.category.is_not(None),
        )
        return {str(category): to_money(amount) for category, amount in self.db.execute(statement)}


class FixedExpenseRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: int,
        amount: Decimal | float | int | str,
        category: str,
        description: str | None = None,
    ) -> FixedExpense:
        fixed_expense = FixedExpense(
            user_id=user_id,
            telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
            amount=to_money(amount),
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

    def total_by_user(self, user_id: int) -> Decimal:
        statement = select(func.sum(FixedExpense.amount)).where(
            FixedExpense.user_id == user_id,
        )
        return to_money(self.db.scalar(statement))

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
        self.try_mark_sent(user_id, sent_on)

    def try_mark_sent(self, user_id: int, sent_on: date) -> bool:
        self.db.add(
            DailyNotification(
                user_id=user_id,
                telegram_user_id=_telegram_user_id_for_user_id(self.db, user_id),
                sent_on=sent_on,
            )
        )
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return False
        return True

    def clear_sent_marker(self, user_id: int, sent_on: date) -> None:
        statement = delete(DailyNotification).where(
            DailyNotification.user_id == user_id,
            DailyNotification.sent_on == sent_on,
        )
        self.db.execute(statement)
        self.db.commit()

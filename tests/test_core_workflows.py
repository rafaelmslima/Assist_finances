import asyncio
import os
import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.database.models import Base
from app.database.repository import (
    BudgetRepository,
    DailyNotificationRepository,
    ExpenseRepository,
    FixedExpenseRepository,
    IncomeRepository,
    UserRepository,
)
from app.services.budget_service import BudgetService
from app.services.expense_service import ExpenseService
from app.services.fixed_expense_service import FixedExpenseService
from app.services.income_service import IncomeService
from app.services.user_service import TelegramUserData, UserService
from app.utils.validators import ParsedBudget, ParsedExpense, ParsedFixedExpense, ParsedIncome


class RepositoryWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def tearDown(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _create_user(self, telegram_user_id: int):
        with self.Session() as db:
            return UserService(UserRepository(db)).register_or_update_from_telegram(
                TelegramUserData(
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=telegram_user_id + 1000,
                    first_name=f"User {telegram_user_id}",
                    username=f"user_{telegram_user_id}",
                )
            )

    def test_user_creation_reuses_existing_internal_user(self):
        first = self._create_user(100)
        second = self._create_user(100)

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.telegram_chat_id, 1100)

    def test_expense_edit_and_delete_are_limited_to_owner(self):
        owner = self._create_user(100)
        other = self._create_user(200)

        with self.Session() as db:
            service = ExpenseService(ExpenseRepository(db))
            expense = service.add_expense(
                owner.id,
                ParsedExpense(amount=25.5, category="mercado", description="almoco"),
            )

            edited_by_other = service.edit_expense(
                other.id,
                expense.id,
                ParsedExpense(amount=99, category="erro", description=None),
            )
            deleted_by_other = service.delete_expense(other.id, expense.id)
            still_exists = ExpenseRepository(db).get_by_id(owner.id, expense.id)

            self.assertIsNone(edited_by_other)
            self.assertFalse(deleted_by_other)
            self.assertIsNotNone(still_exists)
            self.assertEqual(still_exists.amount, 25.5)

            self.assertTrue(service.delete_expense(owner.id, expense.id))
            self.assertIsNone(ExpenseRepository(db).get_by_id(owner.id, expense.id))

    def test_income_budget_and_fixed_expense_use_internal_user_id(self):
        user = self._create_user(300)

        with self.Session() as db:
            income = IncomeService(IncomeRepository(db)).add_income(
                user.id,
                ParsedIncome(amount=3500, description="salario"),
            )
            budget_status = BudgetService(BudgetRepository(db), ExpenseRepository(db))
            budget_status.set_budget(user.id, ParsedBudget(amount=3000, category=None))
            fixed_service = FixedExpenseService(FixedExpenseRepository(db))
            fixed = fixed_service.add_fixed_expense(
                user.id,
                ParsedFixedExpense(amount=800, category="moradia", description="aluguel"),
            )

            self.assertEqual(income.user_id, user.id)
            self.assertEqual(income.telegram_user_id, user.telegram_user_id)
            self.assertEqual(fixed.user_id, user.id)
            self.assertEqual(fixed.telegram_user_id, user.telegram_user_id)
            self.assertEqual(fixed_service.list_fixed_expenses(user.id)["total"], 800)
            self.assertEqual(budget_status.get_budget_status(user.id)["total_budget"], 3000)

    def test_daily_notification_unique_by_user_and_date(self):
        user = self._create_user(400)

        with self.Session() as db:
            notifications = DailyNotificationRepository(db)
            today = date(2026, 4, 28)

            self.assertFalse(notifications.was_sent(user.id, today))
            notifications.mark_sent(user.id, today)
            notifications.mark_sent(user.id, today)

            self.assertTrue(notifications.was_sent(user.id, today))


class SchedulerWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

        with self.Session() as db:
            repo = UserRepository(db)
            self.first_user = repo.create(telegram_user_id=501, telegram_chat_id=1501, first_name="A", username="a")
            self.second_user = repo.create(telegram_user_id=502, telegram_chat_id=1502, first_name="B", username="b")

    def tearDown(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_scheduler_continues_after_user_send_failure(self):
        import app.scheduler as scheduler

        class FakeBot:
            def __init__(self):
                self.sent_chat_ids = []

            async def send_message(self, chat_id: int, text: str) -> None:
                if chat_id == 1501:
                    raise RuntimeError("telegram unavailable")
                self.sent_chat_ids.append(chat_id)

        class FakeApplication:
            def __init__(self):
                self.bot = FakeBot()

        app = FakeApplication()

        with patch.object(scheduler, "SessionLocal", self.Session):
            asyncio.run(scheduler.send_daily_forecasts(app))

        self.assertEqual(app.bot.sent_chat_ids, [1502])
        with self.Session() as db:
            notifications = DailyNotificationRepository(db)
            sent_on = date.today()
            self.assertFalse(notifications.was_sent(self.first_user.id, sent_on))
            self.assertTrue(notifications.was_sent(self.second_user.id, sent_on))


if __name__ == "__main__":
    unittest.main()

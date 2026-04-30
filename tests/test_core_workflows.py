import asyncio
import os
import unittest
from datetime import date, datetime
from io import BytesIO
from unittest.mock import patch

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
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
    SalaryConfigRepository,
    TicketBenefitRepository,
    UpdateBroadcastRepository,
    UserRepository,
)
from app.database.models import Budget, UpdateBroadcast
from app.services.broadcast_service import BroadcastService
from app.services.budget_service import BudgetService
from app.services.analytics_service import AnalyticsService
import app.services.chart_report_service as chart_reports
from app.services.chart_report_service import BUDGET_EMPTY_MESSAGE, ChartReportService
from app.services.date_service import month_range, previous_month
from app.services.expense_service import ExpenseService
from app.services.fixed_expense_service import FixedExpenseService
from app.services.income_service import IncomeService
from app.services.recurring_expense_service import RecurringExpenseService
from app.services.report_service import ReportService
from app.services.salary_service import ParsedSalary, SalaryService, SCHEDULE_FIFTH_BUSINESS_DAY, SCHEDULE_FIXED_DAY, fifth_business_day
from app.services.ticket_service import BENEFIT_ALIMENTACAO, BENEFIT_REFEICAO, PAYMENT_MONEY, PAYMENT_TICKET_ALIMENTACAO, PAYMENT_TICKET_REFEICAO, TicketBalanceError, TicketService
from app.services.user_service import TelegramUserData, UserService
from app.bot.commands import format_recurring_expense_suggestion, format_spending_insights
from app.bot.keyboards import (
    MAIN_BUTTON_ADD_EXPENSE,
    MAIN_BUTTON_AVAILABLE,
    MAIN_BUTTON_CHARTS,
    MAIN_BUTTON_HELP,
    MAIN_BUTTON_INSIGHTS,
    MAIN_BUTTON_MONTH,
    MAIN_BUTTON_SALARY,
    MAIN_BUTTON_TODAY,
    RECURRING_FIXED_NO_CALLBACK,
    RECURRING_FIXED_YES_CALLBACK,
    build_main_reply_keyboard,
    build_recurring_fixed_expense_keyboard,
)
from app.utils.validators import (
    ExpenseValidationError,
    ParsedBudget,
    ParsedExpense,
    ParsedFixedExpense,
    ParsedIncome,
    parse_add_command,
    validate_broadcast_message,
)


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

    def test_main_reply_keyboard_has_essential_commands(self):
        keyboard = build_main_reply_keyboard()

        self.assertEqual(
            keyboard.to_dict()["keyboard"],
            [
                [{"text": "💸 Salvar gasto"}, {"text": "💰 Salario"}],
                [{"text": "📅 Hoje"}, {"text": "📊 Resumo do mes"}],
                [{"text": "📈 Graficos"}, {"text": "🧠 Padroes"}],
                [{"text": "💵 Disponivel"}, {"text": "❓ Ajuda"}],
            ],
        )
        self.assertTrue(keyboard.resize_keyboard)
        self.assertTrue(keyboard.is_persistent)
        self.assertFalse(keyboard.one_time_keyboard)

    def test_recurring_fixed_expense_keyboard_uses_expense_id(self):
        keyboard = build_recurring_fixed_expense_keyboard(123)

        self.assertEqual(
            keyboard.to_dict()["inline_keyboard"],
            [
                [
                    {"text": "✔ Sim", "callback_data": f"{RECURRING_FIXED_YES_CALLBACK}:123"},
                    {"text": "❌ Não", "callback_data": f"{RECURRING_FIXED_NO_CALLBACK}:123"},
                ]
            ],
        )

    def test_user_creation_reuses_existing_internal_user(self):
        first = self._create_user(100)
        second = self._create_user(100)

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.telegram_chat_id, 1100)

    def test_user_input_lengths_are_validated_before_database_write(self):
        with self.assertRaises(ExpenseValidationError):
            parse_add_command(["10", "x" * 81])

        with self.assertRaises(ExpenseValidationError):
            parse_add_command(["10", "mercado", "x" * 256])

        with self.assertRaises(ExpenseValidationError):
            validate_broadcast_message("x" * 4097)

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

    def test_total_budget_is_unique_per_user_and_month_even_without_category(self):
        user = self._create_user(303)

        with self.Session() as db:
            first = Budget(user_id=user.id, telegram_user_id=user.telegram_user_id, month="2026-04", category=None, amount=1000)
            second = Budget(user_id=user.id, telegram_user_id=user.telegram_user_id, month="2026-04", category=None, amount=1200)
            db.add(first)
            db.commit()
            db.add(second)
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_expense_categories_are_distinct_sorted_and_user_scoped(self):
        owner = self._create_user(301)
        other = self._create_user(302)

        with self.Session() as db:
            service = ExpenseService(ExpenseRepository(db))
            service.add_expense(owner.id, ParsedExpense(amount=10, category="mercado", description=None))
            service.add_expense(owner.id, ParsedExpense(amount=20, category="lazer", description=None))
            service.add_expense(owner.id, ParsedExpense(amount=30, category="mercado", description="repetida"))
            service.add_expense(other.id, ParsedExpense(amount=40, category="transporte", description=None))

            self.assertEqual(
                service.get_user_expense_categories(owner.id),
                ["lazer", "mercado"],
            )

    def test_daily_notification_unique_by_user_and_date(self):
        user = self._create_user(400)

        with self.Session() as db:
            notifications = DailyNotificationRepository(db)
            today = date(2026, 4, 28)

            self.assertFalse(notifications.was_sent(user.id, today))
            notifications.mark_sent(user.id, today)
            notifications.mark_sent(user.id, today)

            self.assertTrue(notifications.was_sent(user.id, today))

    def test_update_notification_preference_filters_broadcast_recipients(self):
        opted_in = self._create_user(601)
        opted_out = self._create_user(602)

        with self.Session() as db:
            users = UserRepository(db)
            users.set_receive_updates_notifications(opted_out.id, False)
            recipients = users.list_active_update_recipients()

        self.assertEqual([user.id for user in recipients], [opted_in.id])

    def test_broadcast_continues_after_failure_and_records_summary(self):
        first = self._create_user(701)
        second = self._create_user(702)
        third = self._create_user(703)

        with self.Session() as db:
            UserRepository(db).set_receive_updates_notifications(third.id, False)

        class FakeBot:
            def __init__(self):
                self.sent_chat_ids = []

            async def send_message(self, chat_id: int, text: str) -> None:
                if chat_id == first.telegram_chat_id:
                    raise RuntimeError("blocked")
                self.sent_chat_ids.append(chat_id)

        bot = FakeBot()
        with self.Session() as db:
            result = asyncio.run(
                BroadcastService(
                    UserRepository(db),
                    UpdateBroadcastRepository(db),
                ).send_update_broadcast(bot, admin_user_id=999, message="Novidade")
            )

        self.assertEqual(result.total_users, 2)
        self.assertEqual(result.sent_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(bot.sent_chat_ids, [second.telegram_chat_id])

        with self.Session() as db:
            broadcast = db.scalar(select(UpdateBroadcast))
            self.assertIsNotNone(broadcast)
            self.assertEqual(broadcast.admin_user_id, 999)
            self.assertEqual(broadcast.message, "Novidade")
            self.assertEqual(broadcast.total_users, 2)
            self.assertEqual(broadcast.sent_count, 1)
            self.assertEqual(broadcast.failed_count, 1)

    def test_chart_reports_handle_empty_budget_fixed_and_user_scope(self):
        owner = self._create_user(801)
        other = self._create_user(802)

        with self.Session() as db:
            expense_service = ExpenseService(ExpenseRepository(db))
            owner_expense = expense_service.add_expense(
                owner.id,
                ParsedExpense(amount=120, category="mercado", description="feira"),
            )
            other_expense = expense_service.add_expense(
                other.id,
                ParsedExpense(amount=999, category="viagem", description=None),
            )

            owner_expense.created_at = datetime.now()
            other_expense.created_at = datetime.now()
            db.commit()

            charts = ChartReportService(
                ExpenseRepository(db),
                BudgetRepository(db),
                FixedExpenseRepository(db),
            )

            with _patched_chart_renderers():
                category_report = charts.category(owner.id)
            budget_report = charts.budget_vs_spent(owner.id)
            fixed_report = charts.fixed_vs_variable(owner.id)

        self.assertIsNotNone(category_report.chart)
        self.assertIn("mercado", category_report.text)
        self.assertNotIn("viagem", category_report.text)
        self.assertIsNone(budget_report.chart)
        self.assertEqual(budget_report.text, BUDGET_EMPTY_MESSAGE)
        self.assertIsNone(fixed_report.chart)
        self.assertIn("gastos fixos", fixed_report.text)

    def test_chart_reports_cover_budget_fixed_daily_top_and_month_comparison(self):
        user = self._create_user(803)
        current_start, _ = month_range()
        previous_start, _ = month_range(previous_month())

        with self.Session() as db:
            expense_service = ExpenseService(ExpenseRepository(db))
            current_food = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=200, category="alimentacao", description="mercado"),
            )
            current_transport = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=80, category="transporte", description="metro"),
            )
            previous_food = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=100, category="alimentacao", description=None),
            )
            current_food.created_at = current_start.replace(day=3)
            current_transport.created_at = current_start.replace(day=10)
            previous_food.created_at = previous_start.replace(day=5)

            BudgetService(BudgetRepository(db), ExpenseRepository(db)).set_budget(
                user.id,
                ParsedBudget(amount=150, category="alimentacao"),
            )
            FixedExpenseService(FixedExpenseRepository(db)).add_fixed_expense(
                user.id,
                ParsedFixedExpense(amount=900, category="moradia", description="aluguel"),
            )
            db.commit()

            charts = ChartReportService(
                ExpenseRepository(db),
                BudgetRepository(db),
                FixedExpenseRepository(db),
            )

            with _patched_chart_renderers():
                daily_report = charts.daily_evolution(user.id)
                top_report = charts.top_expenses(user.id)
                comparison_report = charts.month_comparison(user.id)
                budget_report = charts.budget_vs_spent(user.id)
                fixed_report = charts.fixed_vs_variable(user.id)

        self.assertIsNotNone(daily_report.chart)
        self.assertIn("Maior gasto: dia 03", daily_report.text)
        self.assertIsNotNone(top_report.chart)
        self.assertIn("alimentacao", top_report.text)
        self.assertIsNotNone(comparison_report.chart)
        self.assertIn("Mes anterior", comparison_report.text)
        self.assertIsNotNone(budget_report.chart)
        self.assertIn("Categorias acima do limite", budget_report.text)
        self.assertIsNotNone(fixed_report.chart)
        self.assertIn("Fixos previstos", fixed_report.text)

    def test_available_daily_uses_balance_days_remaining_and_historical_excess(self):
        user = self._create_user(804)
        target_date = date(2026, 4, 15)

        with self.Session() as db:
            expense_service = ExpenseService(ExpenseRepository(db))
            income = IncomeService(IncomeRepository(db)).add_income(
                user.id,
                ParsedIncome(amount=3000, description="salario"),
            )
            current_expense = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=900, category="mercado", description=None),
            )
            historical_dates = [date(2026, 3, 10), date(2026, 2, 10), date(2026, 1, 10)]
            historical_expenses = [
                expense_service.add_expense(
                    user.id,
                    ParsedExpense(amount=300, category="mercado", description=None),
                )
                for _ in historical_dates
            ]
            FixedExpenseService(FixedExpenseRepository(db)).add_fixed_expense(
                user.id,
                ParsedFixedExpense(amount=500, category="moradia", description=None),
            )

            income.created_at = datetime(2026, 4, 1)
            current_expense.created_at = datetime(2026, 4, 5)
            for expense, historical_date in zip(historical_expenses, historical_dates):
                expense.created_at = datetime.combine(historical_date, datetime.min.time())
            db.commit()

            result = AnalyticsService(
                ExpenseRepository(db),
                IncomeRepository(db),
                BudgetRepository(db),
                FixedExpenseRepository(db),
            ).get_available_daily_amount(user.id, target_date)

        self.assertEqual(result["remaining_balance"], 1600)
        self.assertEqual(result["days_remaining"], 16)
        self.assertEqual(result["trend"], "normal")
        self.assertEqual(result["daily_amount"], 100)

    def test_smart_summary_flags_budget_usage_and_negative_projection(self):
        user = self._create_user(805)
        target_date = date(2026, 4, 15)

        with self.Session() as db:
            expense_service = ExpenseService(ExpenseRepository(db))
            income = IncomeService(IncomeRepository(db)).add_income(
                user.id,
                ParsedIncome(amount=1000, description="salario"),
            )
            expense = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=900, category="mercado", description=None),
            )
            BudgetRepository(db).upsert(user.id, amount=1000, category=None, target_date=target_date)
            FixedExpenseService(FixedExpenseRepository(db)).add_fixed_expense(
                user.id,
                ParsedFixedExpense(amount=200, category="servicos", description=None),
            )
            income.created_at = datetime(2026, 4, 1)
            expense.created_at = datetime(2026, 4, 4)
            db.commit()

            result = AnalyticsService(
                ExpenseRepository(db),
                IncomeRepository(db),
                BudgetRepository(db),
                FixedExpenseRepository(db),
            ).get_smart_summary(user.id, target_date)

        self.assertEqual(result["monthly_expenses"], 900)
        self.assertEqual(result["current_balance"], 100)
        self.assertEqual(result["available_balance"], -100)
        self.assertEqual(result["fixed_expenses"], 200)
        self.assertEqual(result["budget_used_percent"], 90)
        self.assertIn("Voce ja usou mais de 80% do seu orcamento mensal.", result["alerts"])
        self.assertIn("Seu saldo projetado esta negativo.", result["alerts"])

    def test_salary_cycle_drives_summary_and_available_daily(self):
        user = self._create_user(809)
        target_date = date(2026, 4, 10)

        with self.Session() as db:
            salary_service = SalaryService(SalaryConfigRepository(db), IncomeRepository(db))
            salary_service.configure_salary(
                user.id,
                ParsedSalary(amount=3000, schedule_type=SCHEDULE_FIXED_DAY, pay_day=25),
                received_on=date(2026, 3, 25),
            )
            expense_service = ExpenseService(ExpenseRepository(db))
            in_cycle = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=600, category="mercado", description=None),
            )
            out_of_cycle = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=999, category="lazer", description=None),
            )
            extra_income = IncomeService(IncomeRepository(db)).add_income(
                user.id,
                ParsedIncome(amount=200, description="extra"),
            )
            in_cycle.created_at = datetime(2026, 4, 5)
            out_of_cycle.created_at = datetime(2026, 3, 10)
            extra_income.created_at = datetime(2026, 4, 6)
            db.commit()

            summary = ReportService(
                ExpenseRepository(db),
                SalaryConfigRepository(db),
            ).get_current_month_summary(user.id, target_date)
            available = AnalyticsService(
                ExpenseRepository(db),
                IncomeRepository(db),
                BudgetRepository(db),
                FixedExpenseRepository(db),
                SalaryConfigRepository(db),
            ).get_available_daily_amount(user.id, target_date)

        self.assertEqual(summary["total"], 600)
        self.assertTrue(summary["is_salary_cycle"])
        self.assertEqual(summary["cycle_start"], date(2026, 3, 25))
        self.assertEqual(summary["cycle_end"], date(2026, 4, 23))
        self.assertEqual(available["monthly_income"], 3200)
        self.assertEqual(available["monthly_expenses"], 600)

    def test_available_balance_is_consistent_across_summary_available_and_daily_forecast(self):
        user = self._create_user(811)
        target_date = date(2026, 4, 10)

        with self.Session() as db:
            salary_service = SalaryService(SalaryConfigRepository(db), IncomeRepository(db))
            salary_service.configure_salary(
                user.id,
                ParsedSalary(amount=3000, schedule_type=SCHEDULE_FIXED_DAY, pay_day=1),
                received_on=date(2026, 4, 1),
            )
            expense = ExpenseService(ExpenseRepository(db)).add_expense(
                user.id,
                ParsedExpense(amount=700, category="mercado", description=None),
            )
            FixedExpenseService(FixedExpenseRepository(db)).add_fixed_expense(
                user.id,
                ParsedFixedExpense(amount=500, category="moradia", description=None),
            )
            expense.created_at = datetime(2026, 4, 5)
            db.commit()

            analytics = AnalyticsService(
                ExpenseRepository(db),
                IncomeRepository(db),
                BudgetRepository(db),
                FixedExpenseRepository(db),
                SalaryConfigRepository(db),
            )
            available = analytics.get_available_daily_amount(user.id, target_date)
            summary = analytics.get_smart_summary(user.id, target_date)
            forecast = analytics.get_forecast(user.id, target_date)

        self.assertEqual(available["remaining_balance"], 1800)
        self.assertEqual(summary["available_balance"], 1800)
        self.assertEqual(forecast["available_balance"], 1800)

    def test_ticket_expense_debits_ticket_without_reducing_money_available(self):
        user = self._create_user(812)
        target_date = date(2026, 4, 10)

        with self.Session() as db:
            salary_service = SalaryService(SalaryConfigRepository(db), IncomeRepository(db))
            salary_service.configure_salary(
                user.id,
                ParsedSalary(amount=3000, schedule_type=SCHEDULE_FIXED_DAY, pay_day=1),
                received_on=date(2026, 4, 1),
            )
            ticket_service = TicketService(TicketBenefitRepository(db), SalaryConfigRepository(db))
            ticket_service.configure_benefit(user.id, BENEFIT_ALIMENTACAO, 600, target_date)
            expense_service = ExpenseService(ExpenseRepository(db), ticket_service)
            money_expense = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=500, category="mercado", description=None),
                payment_source=PAYMENT_MONEY,
            )
            ticket_expense = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=200, category="almoco", description=None),
                payment_source=PAYMENT_TICKET_ALIMENTACAO,
            )
            money_expense.created_at = datetime(2026, 4, 5)
            ticket_expense.created_at = datetime(2026, 4, 6)
            db.commit()

            analytics = AnalyticsService(
                ExpenseRepository(db),
                IncomeRepository(db),
                BudgetRepository(db),
                FixedExpenseRepository(db),
                SalaryConfigRepository(db),
                TicketBenefitRepository(db),
            )
            available = analytics.get_available_daily_amount(user.id, target_date)
            summary = analytics.get_smart_summary(user.id, target_date)

        self.assertEqual(available["monthly_expenses"], 500)
        self.assertEqual(available["remaining_balance"], 2500)
        self.assertEqual(summary["available_balance"], 2500)
        self.assertEqual(summary["ticket_summaries"][0].current_balance, 400)
        self.assertEqual(summary["ticket_summaries"][0].spent, 200)

    def test_ticket_expense_is_blocked_when_balance_is_insufficient(self):
        user = self._create_user(813)

        with self.Session() as db:
            ticket_service = TicketService(TicketBenefitRepository(db), SalaryConfigRepository(db))
            ticket_service.configure_benefit(user.id, BENEFIT_REFEICAO, 100, date(2026, 4, 1))

            with self.assertRaises(TicketBalanceError):
                ExpenseService(ExpenseRepository(db), ticket_service).add_expense(
                    user.id,
                    ParsedExpense(amount=150, category="almoco", description=None),
                    payment_source=PAYMENT_TICKET_REFEICAO,
                )

    def test_ticket_balance_reloads_when_cycle_changes(self):
        user = self._create_user(814)

        with self.Session() as db:
            salary_service = SalaryService(SalaryConfigRepository(db), IncomeRepository(db))
            salary_service.configure_salary(
                user.id,
                ParsedSalary(amount=3000, schedule_type=SCHEDULE_FIXED_DAY, pay_day=1),
                received_on=date(2026, 4, 1),
            )
            ticket_service = TicketService(TicketBenefitRepository(db), SalaryConfigRepository(db))
            ticket_service.configure_benefit(user.id, BENEFIT_REFEICAO, 500, date(2026, 4, 1))
            ExpenseService(ExpenseRepository(db), ticket_service).add_expense(
                user.id,
                ParsedExpense(amount=200, category="almoco", description=None),
                payment_source=PAYMENT_TICKET_REFEICAO,
            )
            self.assertEqual(TicketBenefitRepository(db).get_by_type(user.id, BENEFIT_REFEICAO).current_balance, 300)

            ticket_service.refresh_cycle_balances(user.id, date(2026, 5, 2))

            benefit = TicketBenefitRepository(db).get_by_type(user.id, BENEFIT_REFEICAO)

        self.assertEqual(benefit.current_balance, 500)
        self.assertEqual(benefit.cycle_start, date(2026, 5, 1))

    def test_salary_auto_reload_uses_fixed_day_and_avoids_duplicate(self):
        user = self._create_user(810)

        with self.Session() as db:
            salary_service = SalaryService(SalaryConfigRepository(db), IncomeRepository(db))
            salary_service.configure_salary(
                user.id,
                ParsedSalary(amount=3000, schedule_type=SCHEDULE_FIXED_DAY, pay_day=31),
                received_on=date(2026, 1, 31),
            )
            first = salary_service.register_auto_salary_if_due(user.id, date(2026, 2, 28))
            second = salary_service.register_auto_salary_if_due(user.id, date(2026, 2, 28))
            config = SalaryConfigRepository(db).get_by_user(user.id)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(config.current_cycle_start, date(2026, 2, 28))
        self.assertEqual(config.last_auto_salary_on, date(2026, 2, 28))

    def test_fifth_business_day_ignores_weekends(self):
        self.assertEqual(fifth_business_day(2026, 5), date(2026, 5, 7))

    def test_spending_insights_detects_weekend_category_growth_and_current_trend(self):
        user = self._create_user(806)
        target_date = date(2026, 4, 15)

        with self.Session() as db:
            expense_service = ExpenseService(ExpenseRepository(db))
            current_food = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=130, category="alimentacao", description=None),
            )
            current_market = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=770, category="mercado", description=None),
            )
            previous_food = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=100, category="alimentacao", description=None),
            )
            historical_expenses = [
                expense_service.add_expense(
                    user.id,
                    ParsedExpense(amount=100, category="base", description=None),
                )
                for _ in range(3)
            ]

            current_food.created_at = datetime(2026, 4, 4)
            current_market.created_at = datetime(2026, 4, 5)
            previous_food.created_at = datetime(2026, 3, 8)
            historical_expenses[0].created_at = datetime(2026, 3, 2)
            historical_expenses[1].created_at = datetime(2026, 2, 2)
            historical_expenses[2].created_at = datetime(2026, 1, 2)
            db.commit()

            result = AnalyticsService(
                ExpenseRepository(db),
                IncomeRepository(db),
                BudgetRepository(db),
                FixedExpenseRepository(db),
            ).get_spending_insights(user.id, target_date)

        self.assertEqual(result["weekday_pattern"]["type"], "weekend")
        self.assertEqual(result["category_growth"][0]["category"], "alimentacao")
        self.assertEqual(result["category_growth"][0]["percent"], 30.0)
        self.assertEqual(result["trend"], "normal")

        message = format_spending_insights(result)
        self.assertIn("Você gasta mais aos fins de semana", message)
        self.assertIn("alimentacao aumentou 30%", message)
        self.assertIn("Seus gastos estão dentro do normal", message)

    def test_recurring_expense_suggestion_detects_monthly_similar_expense(self):
        user = self._create_user(807)

        with self.Session() as db:
            expense_service = ExpenseService(ExpenseRepository(db))
            previous = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=39.90, category="streaming", description="Netflix"),
            )
            current = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=40.90, category="streaming", description="Netflix"),
            )
            previous.created_at = datetime(2026, 3, 10)
            current.created_at = datetime(2026, 4, 10)
            db.commit()

            suggestion = RecurringExpenseService(
                ExpenseRepository(db),
                FixedExpenseRepository(db),
            ).detect_for_expense(user.id, current)

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.label, "Netflix")
        self.assertEqual(suggestion.occurrences, 2)
        self.assertIn("Netflix - R$ 40,90", format_recurring_expense_suggestion(suggestion))

    def test_recurring_expense_suggestion_skips_existing_similar_fixed_expense(self):
        user = self._create_user(808)

        with self.Session() as db:
            expense_service = ExpenseService(ExpenseRepository(db))
            previous = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=39.90, category="streaming", description="Netflix"),
            )
            current = expense_service.add_expense(
                user.id,
                ParsedExpense(amount=39.90, category="streaming", description="Netflix"),
            )
            previous.created_at = datetime(2026, 3, 10)
            current.created_at = datetime(2026, 4, 10)
            FixedExpenseService(FixedExpenseRepository(db)).add_fixed_expense(
                user.id,
                ParsedFixedExpense(amount=39.90, category="streaming", description="Netflix"),
            )
            db.commit()

            suggestion = RecurringExpenseService(
                ExpenseRepository(db),
                FixedExpenseRepository(db),
            ).detect_for_expense(user.id, current)

        self.assertIsNone(suggestion)


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


def _fake_chart(*_args, **_kwargs):
    return BytesIO(b"chart")


def _patched_chart_renderers():
    return patch.multiple(
        chart_reports,
        build_budget_chart=_fake_chart,
        build_category_chart=_fake_chart,
        build_daily_evolution_chart=_fake_chart,
        build_fixed_variable_chart=_fake_chart,
        build_month_comparison_chart=_fake_chart,
        build_top_expenses_chart=_fake_chart,
    )


if __name__ == "__main__":
    unittest.main()

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.database.models import Income, SalaryConfig
from app.database.repository import IncomeRepository, SalaryConfigRepository
from app.utils.money import to_money


SCHEDULE_FIXED_DAY = "dia_fixo"
SCHEDULE_FIFTH_BUSINESS_DAY = "quinto_dia_util"
SALARY_DESCRIPTION = "salario"


@dataclass(frozen=True)
class ParsedSalary:
    amount: Decimal
    schedule_type: str
    pay_day: int | None


class SalaryService:
    def __init__(
        self,
        salary_config_repository: SalaryConfigRepository,
        income_repository: IncomeRepository,
    ):
        self.salary_config_repository = salary_config_repository
        self.income_repository = income_repository

    def configure_salary(
        self,
        user_id: int,
        parsed_salary: ParsedSalary,
        received_on: date | None = None,
    ) -> tuple[SalaryConfig, Income]:
        received_on = received_on or date.today()
        salary_config = self.salary_config_repository.upsert(
            user_id=user_id,
            amount=parsed_salary.amount,
            schedule_type=parsed_salary.schedule_type,
            pay_day=parsed_salary.pay_day,
            current_cycle_start=received_on,
            is_active=True,
        )
        income = self.income_repository.create(
            user_id=user_id,
            amount=parsed_salary.amount,
            description=SALARY_DESCRIPTION,
            created_at=datetime.combine(received_on, datetime.min.time()),
        )
        return salary_config, income

    def register_manual_salary(
        self,
        user_id: int,
        amount: Decimal,
        received_on: date | None = None,
    ) -> tuple[SalaryConfig, Income]:
        received_on = received_on or date.today()
        salary_config = self.salary_config_repository.get_by_user(user_id)
        schedule_type = salary_config.schedule_type if salary_config else SCHEDULE_FIXED_DAY
        pay_day = salary_config.pay_day if salary_config else received_on.day
        return self.configure_salary(
            user_id,
            ParsedSalary(amount=amount, schedule_type=schedule_type, pay_day=pay_day),
            received_on,
        )

    def register_auto_salary_if_due(
        self,
        user_id: int,
        target_date: date,
    ) -> Income | None:
        salary_config = self.salary_config_repository.get_by_user(user_id)
        if not salary_config or not salary_config.is_active:
            return None
        if salary_config.last_auto_salary_on == target_date:
            return None
        if salary_config.current_cycle_start == target_date:
            return None
        if _scheduled_salary_day(salary_config, target_date) != target_date:
            return None

        income = self.income_repository.create(
            user_id=user_id,
            amount=salary_config.amount,
            description=SALARY_DESCRIPTION,
            created_at=datetime.combine(target_date, datetime.min.time()),
        )
        self.salary_config_repository.set_cycle_start(user_id, target_date)
        self.salary_config_repository.set_last_auto_salary_on(user_id, target_date)
        return income


def _scheduled_salary_day(salary_config: SalaryConfig, target_date: date) -> date | None:
    if salary_config.schedule_type == SCHEDULE_FIFTH_BUSINESS_DAY:
        return fifth_business_day(target_date.year, target_date.month)
    if salary_config.schedule_type == SCHEDULE_FIXED_DAY and salary_config.pay_day:
        last_day = monthrange(target_date.year, target_date.month)[1]
        return date(target_date.year, target_date.month, min(salary_config.pay_day, last_day))
    return None


def fifth_business_day(year: int, month: int) -> date:
    count = 0
    for day in range(1, monthrange(year, month)[1] + 1):
        candidate = date(year, month, day)
        if candidate.weekday() >= 5:
            continue
        count += 1
        if count == 5:
            return candidate
    raise ValueError("Mes sem quinto dia util.")


def schedule_label(schedule_type: str, pay_day: int | None) -> str:
    if schedule_type == SCHEDULE_FIFTH_BUSINESS_DAY:
        return "5o dia util"
    if schedule_type == SCHEDULE_FIXED_DAY and pay_day:
        return f"dia {pay_day}"
    return "manual"

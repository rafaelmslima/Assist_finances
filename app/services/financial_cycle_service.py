from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.database.repository import SalaryConfigRepository
from app.services.date_service import month_range


CYCLE_LENGTH_DAYS = 30


@dataclass(frozen=True)
class FinancialCycle:
    start_date: datetime
    end_date: datetime
    is_salary_cycle: bool

    @property
    def start_day(self) -> date:
        return self.start_date.date()

    @property
    def end_day(self) -> date:
        return (self.end_date - timedelta(days=1)).date()

    def elapsed_days(self, target_date: date | None = None) -> int:
        target_date = target_date or date.today()
        return max((target_date - self.start_day).days + 1, 1)

    def remaining_days(self, target_date: date | None = None) -> int:
        target_date = target_date or date.today()
        return max((self.end_day - target_date).days + 1, 1)

    def total_days(self) -> int:
        return max((self.end_date.date() - self.start_day).days, 1)


class FinancialCycleService:
    def __init__(self, salary_config_repository: SalaryConfigRepository):
        self.salary_config_repository = salary_config_repository

    def current_cycle(self, user_id: int, target_date: date | None = None) -> FinancialCycle:
        target_date = target_date or date.today()
        salary_config = self.salary_config_repository.get_by_user(user_id)
        if salary_config and salary_config.current_cycle_start:
            start_day = salary_config.current_cycle_start
            while target_date >= start_day + timedelta(days=CYCLE_LENGTH_DAYS):
                start_day = start_day + timedelta(days=CYCLE_LENGTH_DAYS)
            end_day = start_day + timedelta(days=CYCLE_LENGTH_DAYS)
            return FinancialCycle(
                start_date=datetime.combine(start_day, time.min),
                end_date=datetime.combine(end_day, time.min),
                is_salary_cycle=True,
            )

        start_date, end_date = month_range(target_date)
        return FinancialCycle(start_date=start_date, end_date=end_date, is_salary_cycle=False)

    def previous_cycle(self, user_id: int, target_date: date | None = None) -> FinancialCycle:
        current = self.current_cycle(user_id, target_date)
        if current.is_salary_cycle:
            previous_end = current.start_date
            previous_start = previous_end - timedelta(days=CYCLE_LENGTH_DAYS)
            return FinancialCycle(
                start_date=previous_start,
                end_date=previous_end,
                is_salary_cycle=True,
            )

        previous_target = current.start_day - timedelta(days=1)
        start_date, end_date = month_range(previous_target)
        return FinancialCycle(start_date=start_date, end_date=end_date, is_salary_cycle=False)

from calendar import monthrange
from datetime import date, datetime, time, timedelta


def month_range(target_date: date | None = None) -> tuple[datetime, datetime]:
    target_date = target_date or date.today()
    start_date = datetime(target_date.year, target_date.month, 1)
    last_day = monthrange(target_date.year, target_date.month)[1]
    end_date = datetime.combine(date(target_date.year, target_date.month, last_day) + timedelta(days=1), time.min)
    return start_date, end_date


def previous_month(target_date: date | None = None) -> date:
    target_date = target_date or date.today()
    if target_date.month == 1:
        return date(target_date.year - 1, 12, 1)
    return date(target_date.year, target_date.month - 1, 1)


def days_in_month(target_date: date | None = None) -> int:
    target_date = target_date or date.today()
    return monthrange(target_date.year, target_date.month)[1]


def elapsed_month_days(target_date: date | None = None) -> int:
    target_date = target_date or date.today()
    return max(target_date.day, 1)


def remaining_month_days(target_date: date | None = None) -> int:
    target_date = target_date or date.today()
    return max(days_in_month(target_date) - target_date.day + 1, 1)


def days_between(start_date: datetime, end_date: datetime) -> int:
    return max((end_date.date() - start_date.date()).days, 1)


def elapsed_period_days(start_date: datetime, target_date: date | None = None) -> int:
    target_date = target_date or date.today()
    return max((target_date - start_date.date()).days + 1, 1)


def remaining_period_days(end_date: datetime, target_date: date | None = None) -> int:
    target_date = target_date or date.today()
    return max(((end_date.date() - target_date).days), 1)


from datetime import date, timedelta

from dateutil.relativedelta import MO, relativedelta


def start_end_date_for_period(
    period: str,
    default_start_date: date | bool = False,
    default_end_date: date | bool = False,
) -> tuple[date | bool, date | bool]:
    today = date.today()
    if period == "daily":
        start_date = today
        end_date = today
    elif period == "weekly":
        start_date = today + relativedelta(weekday=MO(-1))
        end_date = start_date + timedelta(days=6)
    elif period == "monthly":
        start_date = today.replace(day=1)
        end_date = today + relativedelta(months=1, day=1, days=-1)
    elif period == "yearly":
        start_date = today.replace(month=1, day=1)
        end_date = today.replace(month=12, day=31)
    else:
        return (default_start_date, default_end_date)

    return (start_date, end_date)

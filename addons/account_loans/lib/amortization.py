
import calendar
import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

CENT = Decimal("0.01")
PAYMENT_FREQUENCIES = (1, 2, 4, 12)
DAY_COUNT_CONVENTIONS = (
    "30A/360",
    "30U/360",
    "30E/360",
    "30E/360 ISDA",
    "A/360",
    "A/365F",
    "A/A ISDA",
    "A/A AFB",
)


class ScheduleError(ValueError):
    pass


@dataclass(frozen=True)
class Payment:
    date: datetime.date
    principal: Decimal
    interest: Decimal
    balance: Decimal

    @property
    def total(self) -> Decimal:
        return self.principal + self.interest


def _round_to_cents(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _get_month_day_count(value: datetime.date) -> int:
    return calendar.monthrange(value.year, value.month)[1]


def _get_day_count_thirty_day(start, end, convention, period_is_end_of_month):
    d1, d2 = start.day, end.day
    start_eom, end_eom = _get_month_day_count(start), _get_month_day_count(end)
    if convention == "30A/360":
        d1 = min(d1, 30)
        d2 = min(d2, 30) if d1 == 30 else d2
    elif convention == "30U/360":
        if period_is_end_of_month and start.month == 2 and d1 == start_eom:
            if end.month == 2 and d2 == end_eom:
                d2 = 30
            d1 = 30
        if d2 == 31 and d1 >= 30:
            d2 = 30
        if d1 == 31:
            d1 = 30
    elif convention == "30E/360":
        d1 = 30 if d1 == 31 else d1
        d2 = 30 if d2 == 31 else d2
    else:
        d1 = 30 if d1 == start_eom else d1
        d2 = 30 if d2 == end_eom and end.month != 2 else d2
    return 360 * (end.year - start.year) + 30 * (end.month - start.month) + (d2 - d1)


def _get_year_fraction_actual_actual_isda(start, end):

    def get_year_day_count(year):
        return 366 if calendar.isleap(year) else 365

    if start.year == end.year:
        return Decimal((end - start).days) / get_year_day_count(start.year)
    head = Decimal(
        (datetime.date(start.year + 1, 1, 1) - start).days
    ) / get_year_day_count(start.year)
    tail = Decimal((end - datetime.date(end.year, 1, 1)).days) / get_year_day_count(
        end.year
    )
    return head + tail + (end.year - start.year - 1)


def _has_leap_day(start, end) -> bool:
    for year in range(start.year, end.year + 1):
        if calendar.isleap(year) and start < datetime.date(year, 2, 29) <= end:
            return True
    return False


def _get_year_fraction_actual_actual_afb(start, end):
    whole_years = 0
    cursor = end
    while cursor - relativedelta(years=1) >= start:
        cursor -= relativedelta(years=1)
        whole_years += 1
    stub_days = (cursor - start).days
    if not stub_days:
        return Decimal(whole_years)
    denominator = 366 if _has_leap_day(start, cursor) else 365
    return Decimal(whole_years) + Decimal(stub_days) / denominator


def year_fraction(start, end, convention, period_is_end_of_month=False) -> Decimal:
    if convention not in DAY_COUNT_CONVENTIONS:
        raise ScheduleError(f"Unknown day-count convention {convention!r}.")
    if convention.startswith("30"):
        days = _get_day_count_thirty_day(start, end, convention, period_is_end_of_month)
        return Decimal(days) / 360
    if convention == "A/360":
        return Decimal((end - start).days) / 360
    if convention == "A/365F":
        return Decimal((end - start).days) / 365
    if convention == "A/A ISDA":
        return _get_year_fraction_actual_actual_isda(start, end)
    return _get_year_fraction_actual_actual_afb(start, end)


def _get_payment_dates(
    start_date, first_payment_date, count, months_per_period, end_of_month
):
    if first_payment_date is not None:
        anchor = max(first_payment_date, start_date) - relativedelta(
            months=months_per_period
        )
        return [
            anchor + relativedelta(months=months_per_period * period)
            for period in range(1, count + 1)
        ]
    if not end_of_month:
        return [
            start_date + relativedelta(months=months_per_period * period)
            for period in range(1, count + 1)
        ]
    if start_date.day == _get_month_day_count(start_date):
        anchor = start_date
    else:
        anchor = start_date.replace(
            day=_get_month_day_count(start_date)
        ) - relativedelta(months=months_per_period)
    dates = []
    for period in range(1, count + 1):
        moment = anchor + relativedelta(months=months_per_period * period)
        dates.append(moment.replace(day=_get_month_day_count(moment)))
    return dates


def _check_schedule_parameters(
    amount, annual_rate, years, start_date, first_payment_date, frequency, convention
) -> None:
    if not isinstance(amount, (int, float, Decimal)) or amount < 0:
        raise ScheduleError("The loan amount must be a non-negative number.")
    if (
        not isinstance(annual_rate, (int, float, Decimal))
        or not 0 <= annual_rate <= 100
    ):
        raise ScheduleError("The interest rate must be between 0 and 100.")
    if not isinstance(years, int) or years < 1:
        raise ScheduleError(
            "The loan term must be a whole number of years, at least 1."
        )
    if frequency not in PAYMENT_FREQUENCIES:
        raise ScheduleError(f"Payments per year must be one of {PAYMENT_FREQUENCIES}.")
    if convention not in DAY_COUNT_CONVENTIONS:
        raise ScheduleError(f"Unknown day-count convention {convention!r}.")
    if not isinstance(start_date, datetime.date):
        raise ScheduleError("The start date is required.")
    if first_payment_date is not None and first_payment_date < start_date:
        raise ScheduleError("The first payment cannot fall before the start date.")


def generate(
    amount,
    annual_rate,
    years,
    start_date,
    first_payment_date=None,
    end_of_month=True,
    payments_per_year=12,
    convention="30E/360",
):
    _check_schedule_parameters(
        amount,
        annual_rate,
        years,
        start_date,
        first_payment_date,
        payments_per_year,
        convention,
    )
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.date()

    count = years * payments_per_year
    months_per_period = 12 // payments_per_year
    dates = _get_payment_dates(
        start_date, first_payment_date, count, months_per_period, end_of_month
    )

    amount = Decimal(str(amount))
    rate = Decimal(str(annual_rate)) / 100
    if rate:
        periodic_rate = rate / payments_per_year
        growth = (1 + periodic_rate) ** count
        instalment = amount * periodic_rate * growth / (growth - 1)
    else:
        instalment = amount / count

    schedule = []
    balance = amount
    previous_date = start_date
    for index, payment_date in enumerate(dates):
        if rate:
            factor = year_fraction(
                previous_date, payment_date, convention, end_of_month
            )
            interest = _round_to_cents(balance * rate * factor)
            principal = _round_to_cents(instalment) - interest
        else:
            interest = Decimal("0.00")
            principal = _round_to_cents(instalment)
        if index == count - 1:
            principal = balance
        principal = max(Decimal("0.00"), min(principal, balance))
        balance -= principal
        schedule.append(
            Payment(
                date=payment_date,
                principal=principal,
                interest=interest,
                balance=balance,
            )
        )
        previous_date = payment_date
    return schedule

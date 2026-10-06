from math import ceil


def round_time_spent(minutes_spent, minimum, rounding):
    minutes_spent = max(minimum, minutes_spent)
    if rounding:
        minutes_spent = ceil(minutes_spent / rounding) * rounding
    return minutes_spent

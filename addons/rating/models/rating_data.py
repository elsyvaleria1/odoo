from datetime import timedelta

from odoo.libs.numbers import float_compare
from odoo.tools import DOMAIN_PREDICATES, SET_DOMAIN_OPERATORS

RATING_AVG_TOP = 3.66
RATING_AVG_OK = 2.33
RATING_AVG_MIN = 1

RATING_LIMIT_SATISFIED = 4
RATING_LIMIT_OK = 3
RATING_LIMIT_MIN = 1
RATING_HAPPY_VALUE = 5
RATING_NEUTRAL_VALUE = 3
RATING_UNHAPPY_VALUE = 1
RATING_NONE_VALUE = 0
# how long a customer may still change the rating they gave through its link;
# the notification of the rating waits as long
RATING_CHANGE_WINDOW = timedelta(hours=2)

RATING_TEXT = [
    ("top", "Happy"),
    ("ok", "Neutral"),
    ("ko", "Unhappy"),
    ("none", "Not Rated yet"),
]


def _rating_avg_satisfies(operator, rating_avg, value):
    if operator in SET_DOMAIN_OPERATORS:
        found = any(float_compare(rating_avg, element, 2) == 0 for element in value)
        return found if operator == "in" else not found
    return DOMAIN_PREDICATES[operator](float_compare(rating_avg, value, 2), 0)


def _rating_avg_to_text(rating_avg) -> str:
    if float_compare(rating_avg, RATING_AVG_TOP, 2) >= 0:
        return "top"
    if float_compare(rating_avg, RATING_AVG_OK, 2) >= 0:
        return "ok"
    if float_compare(rating_avg, RATING_AVG_MIN, 2) >= 0:
        return "ko"
    return "none"


def _rating_assert_value(rating_value) -> None:
    assert RATING_NONE_VALUE <= rating_value <= RATING_HAPPY_VALUE


def _rating_to_grade(rating_value) -> str:
    """Return the grade bucket ('great', 'okay', 'bad') for a rating value."""
    _rating_assert_value(rating_value)
    if rating_value >= RATING_LIMIT_SATISFIED:
        return "great"
    if rating_value >= RATING_LIMIT_OK:
        return "okay"
    return "bad"


def _rating_to_text(rating_value) -> str:
    """From a rating value give a text-based mean value."""
    _rating_assert_value(rating_value)
    if rating_value >= RATING_LIMIT_SATISFIED:
        return "top"
    if rating_value >= RATING_LIMIT_OK:
        return "ok"
    if rating_value >= RATING_LIMIT_MIN:
        return "ko"
    return "none"


def _rating_to_threshold(rating_value):
    """From a rating value, return the thresholds in form of 0-1-3-5 used
    notably for images."""
    _rating_assert_value(rating_value)
    if rating_value >= RATING_LIMIT_SATISFIED:
        return RATING_HAPPY_VALUE
    if rating_value >= RATING_LIMIT_OK:
        return RATING_NEUTRAL_VALUE
    if rating_value >= RATING_LIMIT_MIN:
        return RATING_UNHAPPY_VALUE
    return RATING_NONE_VALUE

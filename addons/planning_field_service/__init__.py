from . import models

PUBLISHED_SHIFTS_ROW = "planning.planning_rule_user_is_published"


def _hide_visits_from_colleagues(env) -> None:
    env.ref(PUBLISHED_SHIFTS_ROW).active = False


def _show_published_shifts_again(env) -> None:
    row = env.ref(PUBLISHED_SHIFTS_ROW, raise_if_not_found=False)
    if row:
        row.active = True

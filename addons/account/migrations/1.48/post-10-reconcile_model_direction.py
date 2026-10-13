import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _signed_condition_to_absolute(match_amount, minimum, maximum):
    minimum = minimum or 0.0
    maximum = maximum or 0.0
    if match_amount == "lower":
        low, high = None, maximum
    elif match_amount == "greater":
        low, high = minimum, None
    elif match_amount == "between":
        low, high = min(minimum, maximum), max(minimum, maximum)
    else:
        return "both", False, 0.0, 0.0, True
    if match_amount == "between" and not (minimum or maximum):
        return "both", "lower", 0.0, 0.0, True
    if low is not None and low >= 0.0:
        return "incoming", *_size_condition(low, high), True
    if high is not None and high <= 0.0:
        return "outgoing", *_size_condition(-high, None if low is None else -low), True
    bound = max(abs(value) for value in (low, high) if value is not None)
    return "both", "lower", 0.0, bound, False


def _size_condition(smallest, largest):
    if largest is None:
        return ("greater", smallest, 0.0) if smallest else (False, 0.0, 0.0)
    if smallest:
        return "between", smallest, largest
    return "lower", 0.0, largest


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        SELECT id, match_amount, match_amount_min, match_amount_max
          FROM account_reconcile_model
         WHERE match_amount IS NOT NULL
            OR match_amount_min < 0
            OR match_amount_max < 0
         ORDER BY id
        """
    )
    straddling_ids = []
    for model_id, *old in cr.fetchall():
        direction, *new, exact = _signed_condition_to_absolute(*old)
        cr.execute(
            """
            UPDATE account_reconcile_model
               SET match_direction = %s,
                   match_amount = %s,
                   match_amount_min = %s,
                   match_amount_max = %s
             WHERE id = %s
            """,
            [direction, new[0] or None, new[1], new[2], model_id],
        )
        log = _logger.info if exact else _logger.warning
        log(
            "account.reconcile.model %s: signed amount condition %s (min %s, max %s)"
            " became direction %s, absolute amount condition %s (min %s, max %s)%s",
            model_id,
            *old,
            direction,
            *new,
            ""
            if exact
            else "; the old condition straddled zero, so the direction no longer"
            " restricts it and its size bound now applies to both directions",
        )
        if not exact:
            straddling_ids.append(model_id)
    if straddling_ids:
        env = api.Environment(cr, SUPERUSER_ID, {})
        env["account.reconcile.model"].browse(
            straddling_ids
        )._refresh_statement_line_proposals(auto_reconcile=False)

import logging
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import PosLazySessionCommon

_logger = logging.getLogger(__name__)


def _get_counted(original, calls):
    def counted(records):
        calls.append(records.ids)
        return original(records)

    return counted


@tagged("post_install", "-at_install")
class TestPosPaymentMethodOpenSessions(PosLazySessionCommon):
    def test_an_open_session_blocks_edits_through_a_warm_cache(self):
        method = self.bank_payment_method
        before = method.open_session_ids
        self.assertFalse(before)
        session = self._ensure_session()
        cached = method.open_session_ids
        with self.assertRaises(UserError):
            method.write({"name": "Mutation while session open"})
        method.invalidate_recordset(["open_session_ids"])
        fresh = method.open_session_ids
        _logger.debug(
            "payment guard cached=%s fresh=%s session=%s",
            cached.ids,
            fresh.ids,
            session.id,
        )
        self.assertIn(session, cached)
        self.assertIn(session, fresh)
        with self.assertRaises(UserError):
            method.write({"name": "Blocked after invalidation"})

    def test_a_disabled_lifecycle_log_does_not_compute_the_open_sessions(self):
        from odoo.addons.point_of_sale.models import pos_payment_method

        method = self.bank_payment_method
        original = type(method)._compute_open_session_ids
        for enabled in [False, True]:
            calls = []
            method.invalidate_recordset(["open_session_ids"])
            with (
                patch.object(
                    type(method),
                    "_compute_open_session_ids",
                    _get_counted(original, calls),
                ),
                patch.object(
                    pos_payment_method._debug.lifecycle.logger,
                    "isEnabledFor",
                    return_value=enabled,
                ),
            ):
                method.write({"sequence": method.sequence + 1})
            _logger.debug(
                "debug-label lifecycle_enabled=%s computed_calls=%s",
                enabled,
                calls,
            )
            self.assertEqual(len(calls), int(enabled))

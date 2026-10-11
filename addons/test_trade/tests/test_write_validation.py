from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .common import TestTradeOrderCase


@tagged("post_install", "-at_install")
class TestWriteValidation(TestTradeOrderCase):
    def test_locked_business_field_write_blocked_when_locked(self):
        order = self._make_order()
        order.write({"state": "done"})
        order.write({"locked": True})

        with self.assertRaises(UserError):
            order.write({"partner_ref": "REF-123"})

    def test_locked_writable_field_allowed_when_locked(self):
        order = self._make_order()
        order.write({"state": "done", "locked": True})

        order.write({"priority": "1"})

        self.assertEqual(order.priority, "1")

    def test_illegal_state_transition_blocked(self):
        order = self._make_order()
        order.write({"state": "done"})

        with self.assertRaises(UserError):
            order.write({"state": "draft"})

    def test_legal_state_transition_allowed(self):
        order = self._make_order()

        order.write({"state": "done"})

        self.assertEqual(order.state, "done")

    def test_writing_an_unchanged_value_on_a_locked_order_is_allowed(self):
        order = self._make_order()
        order.write({"state": "done", "locked": True})
        unchanged = order.date_order

        order.write({"date_order": unchanged.strftime("%Y-%m-%d %H:%M:%S")})

        self.assertEqual(order.date_order, unchanged)

    def test_writing_an_unchanged_datetime_object_is_allowed(self):
        order = self._make_order()
        order.write({"state": "done", "locked": True})
        unchanged = order.date_order

        order.write({"date_order": unchanged})

        self.assertEqual(order.date_order, unchanged)

    def test_writing_an_unchanged_x2many_on_a_locked_order_is_allowed(self):
        order = self._make_order()
        line = self._make_line(order=order)
        order.write({"state": "done", "locked": True})

        order.write({"line_ids": [Command.set(order.line_ids.ids)]})

        self.assertEqual(order.line_ids, line)

    def test_a_real_change_on_a_locked_order_is_still_refused(self):
        order = self._make_order()
        order.write({"state": "done", "locked": True})

        with self.assertRaises(UserError):
            order.write({"date_order": "2020-01-01 00:00:00"})

    def test_a_real_x2many_change_on_a_locked_order_is_still_refused(self):
        order = self._make_order()
        self._make_line(order=order)
        order.write({"state": "done", "locked": True})

        with self.assertRaises(UserError):
            order.write({"line_ids": [Command.clear()]})

    def test_a_misspelled_write_guard_raises_rather_than_being_skipped(self):
        order = self._make_order()
        model = type(self.env["test_trade.order"])
        original = model._get_check_write_guards
        model._get_check_write_guards = lambda self: ["_check_write_guard_typo"]
        try:
            with self.assertRaises(AttributeError):
                order.write({"partner_ref": "X"})
        finally:
            model._get_check_write_guards = original

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestDefaultGanttView(TransactionCase):
    """Cover the default gantt view derived for models without one."""

    def test_default_view_without_date_fields_is_refused(self):
        """A model with no usable date field cannot get a gantt view."""
        # ir.model declares none of the accepted start/stop field names.
        with self.assertRaises(UserError):
            self.env["ir.model"]._get_default_gantt_view()

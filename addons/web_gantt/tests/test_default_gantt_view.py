from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestDefaultGanttView(TransactionCase):

    def test_default_view_without_date_fields_is_refused(self):
        with self.assertRaises(UserError):
            self.env["ir.model"]._get_default_gantt_view()

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase


class TestWorksheetReportAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref("base.group_user")
        cls.owner, cls.outsider = cls.env["res.users"].create(
            [
                {
                    "name": "Order owner",
                    "login": "worksheet_owner",
                    "group_ids": [(6, 0, [group_user.id])],
                },
                {
                    "name": "Outsider",
                    "login": "worksheet_outsider",
                    "group_ids": [(6, 0, [group_user.id])],
                },
            ]
        )
        cls.order = (
            cls.env["maintenance.order"]
            .with_user(cls.owner)
            .create({"name": "Owner order", "user_id": cls.owner.id})
        )

    def _render_as(self, user):
        return (
            self.env["ir.actions.report"]
            .with_user(user)
            ._render_qweb_html(
                "maintenance_worksheet.maintenance_worksheet", self.order.ids
            )
        )

    def test_a_user_who_cannot_read_the_order_cannot_print_it(self):
        with self.assertRaises(AccessError):
            self._render_as(self.outsider)

    def test_a_user_who_can_read_the_order_prints_it(self):
        html, _format = self._render_as(self.owner)
        self.assertIn(b"Owner order", html)

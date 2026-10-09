from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.pos_pine_labs.models.pine_labs_pos_request import (
    pine_labs_request_body,
)


@tagged("post_install", "-at_install")
class TestPineLabsCredentials(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.method = cls.env["pos.payment.method"].create(
            {"name": "Pine Labs", "pine_labs_security_token": "security-token"}
        )
        cls.cashier = new_test_user(
            cls.env, "pine_labs_cashier", groups="point_of_sale.group_pos_user"
        )

    def test_a_cashier_reads_no_security_token(self):
        with self.assertRaises(AccessError):
            self.method.with_user(self.cashier).read(["pine_labs_security_token"])

    def test_a_cashier_request_still_carries_it(self):
        body = pine_labs_request_body(False, self.method.with_user(self.cashier))

        self.assertEqual(body["SecurityToken"], "security-token")

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestTyroCredentials(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.method = cls.env["pos.payment.method"].create(
            {
                "name": "Tyro",
                "use_payment_terminal": "tyro",
                "tyro_merchant_id": "m",
                "tyro_terminal_id": "t",
                "tyro_integration_key": "integration-key",
            }
        )
        cls.till = cls.env["pos.config"].create(
            {"name": "Tyro till", "payment_method_ids": [Command.link(cls.method.id)]}
        )
        cls.other_till = cls.env["pos.config"].create(
            {"name": "Another till", "payment_method_ids": [Command.set([])]}
        )
        cls.cashier = new_test_user(
            cls.env, "tyro_cashier", groups="point_of_sale.group_pos_user"
        )

    def test_a_cashier_reads_no_integration_key(self):
        method = self.method.with_user(self.cashier)
        with self.assertRaises(AccessError):
            method.read(["tyro_integration_key"])
        with self.assertRaises(AccessError):
            method.action_get_tyro_report()

    def test_only_the_till_driving_the_terminal_loads_it(self):
        PaymentMethod = self.env["pos.payment.method"].with_user(self.cashier)
        method = self.method.with_user(self.cashier)

        [row] = PaymentMethod._load_pos_data_read(method, self.till)
        [elsewhere] = PaymentMethod._load_pos_data_read(method, self.other_till)

        self.assertEqual(row["tyro_integration_key"], "integration-key")
        self.assertEqual(row["tyro_terminal_id"], "t")
        self.assertFalse(elsewhere["tyro_integration_key"])

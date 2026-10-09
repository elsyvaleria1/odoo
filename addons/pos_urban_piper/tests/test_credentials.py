from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestUrbanPiperCredentials(TransactionCase):
    def test_only_a_pos_manager_reads_the_api_key(self):
        self.env.company.pos_urbanpiper_apikey = "urbanpiper-key"
        employee = new_test_user(self.env, "up_employee", groups="base.group_user")
        cashier = new_test_user(
            self.env, "up_cashier", groups="point_of_sale.group_pos_user"
        )
        manager = new_test_user(
            self.env, "up_manager", groups="point_of_sale.group_pos_manager"
        )

        for user in (employee, cashier):
            with self.subTest(user.login), self.assertRaises(AccessError):
                self.env.company.with_user(user).read(["pos_urbanpiper_apikey"])
        self.assertEqual(
            self.env.company.with_user(manager).pos_urbanpiper_apikey,
            "urbanpiper-key",
        )

from odoo.tests import new_test_user, tagged

from odoo.addons.bus.tools.channel_capability import resolve_capability
from odoo.addons.point_of_sale.tests.common import CommonPosTest


@tagged("post_install", "-at_install")
class TestPosBusToken(CommonPosTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cashier = new_test_user(
            cls.env,
            login="pos_bus_token_cashier",
            groups="base.group_user,point_of_sale.group_pos_user",
            company_id=cls.company.id,
        )

    def test_order_bus_token_is_the_orders_own_column(self):
        order, _refund = self.create_backend_pos_order({})
        order.sudo().access_token = False
        bus_token = order.with_user(self.cashier)._pos_bus_get_or_create_token()
        self.assertTrue(bus_token)
        self.assertEqual(order.sudo().access_token, bus_token)
        self.assertEqual(
            order.with_user(self.cashier)._pos_bus_get_or_create_token(), bus_token
        )

    def test_rotating_gives_each_config_a_fresh_token_of_the_minted_shape(self):
        configs = self.pos_config_usd | self.pos_config_eur
        before = configs.mapped("access_token")
        configs._pos_bus_rotate_token()
        after = configs.mapped("access_token")
        self.assertEqual(len(set(after)), 2)
        self.assertFalse(set(before) & set(after))
        self.assertEqual({len(token) for token in before + after}, {36})

    def test_a_till_channel_resolves_only_for_a_user_who_reads_its_point_of_sale(self):
        config = self.pos_config_usd
        till = config._pos_bus_channel("till")
        display = config._pos_bus_channel("customer_display")
        public = self.env.ref("base.public_user")
        portal = new_test_user(
            self.env, login="pos_bus_token_portal", groups="base.group_portal"
        )
        self.assertTrue(resolve_capability(self.env(user=self.cashier), till))
        for user in (public, portal):
            with self.subTest(user=user.id):
                self.assertIsNone(resolve_capability(self.env(user=user), till))
                self.assertTrue(resolve_capability(self.env(user=user), display))

    def test_a_till_of_a_cashiers_other_company_is_theirs_and_no_one_elses(self):
        second = self.env["res.company"].sudo().create({"name": "Second shop"})
        till = self.pos_config_usd._pos_bus_channel("till")
        both = new_test_user(
            self.env,
            login="pos_bus_token_both",
            groups="base.group_user,point_of_sale.group_pos_user",
            company_id=second.id,
            company_ids=[second.id, self.pos_config_usd.company_id.id],
        )
        other = new_test_user(
            self.env,
            login="pos_bus_token_other",
            groups="base.group_user,point_of_sale.group_pos_user",
            company_id=second.id,
            company_ids=[second.id],
        )
        self.assertTrue(resolve_capability(self.env(user=both), till))
        self.assertIsNone(resolve_capability(self.env(user=other), till))

import odoo
from odoo import Command

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged("post_install", "-at_install")
class TestConfigureShops(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_order_template = cls.env.ref(
            "sale.group_sale_order_template", raise_if_not_found=False
        )
        if group_order_template:
            cls.env.ref("base.group_user").write(
                {"implied_ids": [(4, group_order_template.id)]}
            )

    def _remove_on_payment_taxes(self):
        self.env["account.tax"].search(
            [
                ("company_ids", "in", [self.env.company.id]),
                ("tax_exigibility", "=", "on_payment"),
            ]
        ).unlink()

    def test_properly_set_pos_config_x2many_fields(self):

        self._remove_on_payment_taxes()
        pos_config = self.env["pos.config"].create(
            {
                "name": "Shop 1",
                "module_pos_restaurant": False,
                "payment_method_ids": [
                    Command.create(
                        {
                            "name": "Bank 1",
                            "receivable_account_id": self.env.company.account_config_id.account_default_pos_receivable_account_id.id,
                            "is_cash_count": False,
                            "split_transactions": False,
                            "company_id": self.env.company.id,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Bank 2",
                            "receivable_account_id": self.env.company.account_config_id.account_default_pos_receivable_account_id.id,
                            "is_cash_count": False,
                            "split_transactions": False,
                            "company_id": self.env.company.id,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Cash",
                            "receivable_account_id": self.env.company.account_config_id.account_default_pos_receivable_account_id.id,
                            "is_cash_count": True,
                            "company_id": self.env.company.id,
                        }
                    ),
                ],
            }
        )

        linked_ids = pos_config.payment_method_ids.ids
        second_id = linked_ids[1]
        commands = [Command.link(_id) for _id in linked_ids if _id != second_id]

        pos_config.with_context(from_settings_view=True).write(
            {"payment_method_ids": commands}
        )

        self.assertTrue(second_id not in pos_config.payment_method_ids.ids)
        self.assertTrue(len(pos_config.payment_method_ids) == 2)

    def test_write_default_and_available_presets_on_multiple_pos_configs(self):
        preset = self.env["pos.preset"].create({"name": "Preset 1"})

        pos_config1 = self.env["pos.config"].create(
            {"name": "Shop 1", "module_pos_restaurant": False}
        )
        pos_config2 = self.env["pos.config"].create(
            {"name": "Shop 2", "module_pos_restaurant": False}
        )
        pos_config3 = self.env["pos.config"].create(
            {"name": "Shop 3", "module_pos_restaurant": False}
        )

        pos_configs = pos_config1 | pos_config2 | pos_config3

        pos_configs.write(
            {
                "use_presets": True,
                "available_preset_ids": [(6, 0, [preset.id])],
                "default_preset_id": preset.id,
            }
        )

    def _shop(self, name):
        return self.env["pos.config"].create({"name": name})

    def test_trust_between_configs_is_mutual(self):
        shop_a, shop_b, shop_c = (self._shop(name) for name in "ABC")

        shop_a.trusted_config_ids = shop_b | shop_c

        self.assertEqual(shop_b.trusted_config_ids, shop_a)
        self.assertEqual(shop_c.trusted_config_ids, shop_a)

        shop_a.trusted_config_ids = shop_c

        self.assertFalse(shop_b.trusted_config_ids)
        self.assertEqual(shop_c.trusted_config_ids, shop_a)

    def test_a_new_config_is_trusted_back(self):
        shop_a = self._shop("A")

        shop_b = self.env["pos.config"].create(
            {"name": "B", "trusted_config_ids": [Command.set(shop_a.ids)]}
        )

        self.assertEqual(shop_a.trusted_config_ids, shop_b)

    def test_editing_trust_in_settings_writes_nothing_until_saved(self):
        shop_a, shop_b = self._shop("A"), self._shop("B")
        shop_a.trusted_config_ids = shop_b
        settings = self.env["res.config.settings"].create({"pos_config_id": shop_a.id})

        settings.onchange(
            {"pos_config_id": shop_a.id, "pos_trusted_config_ids": [Command.clear()]},
            ["pos_trusted_config_ids"],
            {"pos_config_id": {}, "pos_trusted_config_ids": {}},
        )

        self.env.invalidate_all()
        self.assertEqual(shop_b.trusted_config_ids, shop_a)

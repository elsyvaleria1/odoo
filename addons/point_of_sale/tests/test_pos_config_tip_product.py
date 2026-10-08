import logging

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosConfigTipProduct(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.product = cls.env["product.product"].create(
            {
                "name": "Tip candidate",
                "available_in_pos": True,
                "taxes_id": [Command.clear()],
            }
        )

    def test_tip_fallback_excludes_foreign_and_archived_products(self):
        foreign = self.env["res.company"].create({"name": "Foreign tips"})
        default = self.env.ref("point_of_sale.product_product_tip")
        default.company_id = foreign
        local = self.product.copy(
            {"default_code": "TIPS", "company_id": self.env.company.id}
        )
        configs = self.env["pos.config"].with_context(
            allowed_company_ids=[self.env.company.id, foreign.id], active_test=False
        )
        _logger.debug(
            "Tip fallback company=%s foreign=%s local=%s",
            self.env.company.id,
            default.id,
            local.id,
        )
        self.assertEqual(configs._default_tip_product_id(), local)
        local.active = False
        self.assertFalse(configs._default_tip_product_id())

    def test_tip_reset_uses_configuration_company(self):
        foreign = self.env["res.company"].create({"name": "Active foreign tips"})
        default = self.env.ref("point_of_sale.product_product_tip")
        default.company_id = foreign
        local = self.product.copy(
            {"default_code": "TIPS", "company_id": self.config.company_id.id}
        )
        config = self.config.with_context(
            allowed_company_ids=[foreign.id, self.config.company_id.id]
        )
        config.write({"iface_tipproduct": True, "tip_product_id": False})
        _logger.debug(
            "Tip reset active company=%s config company=%s product=%s",
            foreign.id,
            config.company_id.id,
            config.tip_product_id.id,
        )
        self.assertEqual(config.tip_product_id, local)

    def test_explicit_foreign_tip_is_rejected(self):
        foreign = self.env["res.company"].create({"name": "Explicit foreign tip"})
        product = self.product.copy({"company_id": foreign.id})
        config = self.config.with_context(
            allowed_company_ids=[self.config.company_id.id, foreign.id]
        )
        _logger.debug(
            "Rejecting explicit foreign tip %s for config %s", product.id, config.id
        )
        with self.assertRaises(UserError):
            config.tip_product_id = product

    def test_batch_tip_reset_uses_each_configuration_company(self):
        company = self.env["res.company"].create({"name": "Batch tip company"})
        self.env["account.chart.template"].try_loading(
            "generic_coa", company=company, install_demo=False
        )
        other = self.env["pos.config"].create(
            {"name": "Other tips", "company_id": company.id}
        )
        default = self.env.ref("point_of_sale.product_product_tip")
        default.company_id = company
        local = self.product.copy(
            {"default_code": "TIPS", "company_id": self.config.company_id.id}
        )
        configs = (self.config | other).with_context(
            allowed_company_ids=[self.config.company_id.id, company.id]
        )
        configs.write(
            {
                "iface_tipproduct": True,
                "tip_product_id": False,
                "available_preset_ids": [
                    Command.create({"name": "Shared cross-company preset"})
                ],
            }
        )
        _logger.debug("Batch tip products: %s", configs.tip_product_id.ids)
        self.assertEqual(configs[0].tip_product_id, local)
        self.assertEqual(configs[1].tip_product_id, default)
        presets = self.env["pos.preset"].search(
            [("name", "=", "Shared cross-company preset")]
        )
        self.assertEqual(len(presets), 1)
        self.assertTrue(
            all(presets in config.available_preset_ids for config in configs)
        )

    def test_batch_tip_reset_preserves_shared_many2many_create(self):
        configs = self.config | self.config.copy({"name": "Batch command peer"})
        configs.write(
            {
                "iface_tipproduct": True,
                "tip_product_id": False,
                "available_preset_ids": [
                    Command.create({"name": "Shared batch preset"})
                ],
            }
        )
        presets = self.env["pos.preset"].search([("name", "=", "Shared batch preset")])
        _logger.debug(
            "Tip reset with batch CREATE: presets=%s config presets=%s",
            presets.ids,
            configs.available_preset_ids.ids,
        )
        self.assertEqual(
            len(presets), 1, "A many2many batch CREATE must create one shared record"
        )
        self.assertTrue(
            all(presets in config.available_preset_ids for config in configs)
        )

    def test_special_products_are_the_configs_own(self):
        tip = self.env["product.product"].create(
            {"name": "Custom Tip", "available_in_pos": True}
        )
        self.config.tip_product_id = tip
        self.assertIn(tip, self.config._get_special_products())
        payload = self.env["pos.config"]._load_pos_data_read(self.config, self.config)
        self.assertIn(tip.id, payload[0]["_pos_special_products_ids"])

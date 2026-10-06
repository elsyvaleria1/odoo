import odoo

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.pos_urban_piper.models.account_chart_template import (
    URBANPIPER_FISCAL_POSITION,
)


@odoo.tests.tagged("post_install", "-at_install")
class TestUrbanPiperCompanyConsistency(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("point_of_sale.group_pos_manager")
        cls.main_company = cls.env.company
        cls.other_company = cls.setup_other_company()["company"]
        cls.shipped_position = cls._shipped_position(cls.main_company)
        cls.other_shipped_position = cls._shipped_position(cls.other_company)

    @classmethod
    def _shipped_position(cls, company):
        return (
            cls.env["account.chart.template"]
            .with_company(company)
            .ref(URBANPIPER_FISCAL_POSITION, raise_if_not_found=False)
        )

    def _create_config(self, **vals):
        return self.env["pos.config"].create(
            {"name": "Urban Piper Other Store", "company_id": self.other_company.id}
            | vals
        )

    def test_a_chart_loaded_after_install_ships_the_company_position(self):
        self.assertEqual(self.shipped_position.name, "Urbanpiper")
        self.assertEqual(self.shipped_position.company_id, self.main_company)
        self.assertEqual(self.other_shipped_position.name, "Urbanpiper")
        self.assertEqual(self.other_shipped_position.company_id, self.other_company)

    def test_a_config_of_another_company_takes_no_foreign_position(self):
        self.other_shipped_position.unlink()
        config = self._create_config()
        self.assertFalse(config.urbanpiper_fiscal_position_id)

    def test_a_config_of_another_company_takes_that_company_position(self):
        config = self._create_config()
        self.assertEqual(
            config.urbanpiper_fiscal_position_id, self.other_shipped_position
        )

    def test_a_config_takes_a_position_named_urbanpiper_when_none_is_shipped(self):
        self.other_shipped_position.unlink()
        position = self.env["account.fiscal.position"].create(
            {"name": "UrbanPiper", "company_id": self.other_company.id}
        )
        config = self._create_config()
        self.assertEqual(config.urbanpiper_fiscal_position_id, position)

    def test_a_config_of_the_main_company_takes_the_shipped_position(self):
        config = self.env["pos.config"].create({"name": "Urban Piper Main Store"})
        self.assertEqual(config.urbanpiper_fiscal_position_id, self.shipped_position)

    def test_enabling_urban_piper_creates_the_position_in_the_config_company(self):
        self.other_shipped_position.unlink()
        config = self._create_config(module_pos_urban_piper=True)
        position = config.urbanpiper_fiscal_position_id
        self.assertTrue(position)
        self.assertEqual(position.company_id, self.other_company)
        self.assertEqual(config.urbanpiper_pricelist_id.company_id, self.other_company)

    def test_a_second_config_of_the_company_reuses_its_position(self):
        first = self._create_config(module_pos_urban_piper=True)
        second = self._create_config(
            name="Urban Piper Other Store 2", module_pos_urban_piper=True
        )
        self.assertEqual(
            first.urbanpiper_fiscal_position_id, self.other_shipped_position
        )
        self.assertEqual(
            second.urbanpiper_fiscal_position_id, first.urbanpiper_fiscal_position_id
        )

    def test_a_chart_loaded_before_install_gets_the_position_from_the_hook(self):
        self.shipped_position.unlink()
        self.assertFalse(self._shipped_position(self.main_company))
        self.env["account.chart.template"].sudo()._load_urbanpiper_fiscal_positions()
        position = self._shipped_position(self.main_company)
        self.assertEqual(position.name, "Urbanpiper")
        self.assertEqual(position.company_id, self.main_company)

    def test_the_hook_adopts_a_position_the_company_already_has(self):
        self.shipped_position.unlink()
        existing = self.env["account.fiscal.position"].create(
            {"name": "UrbanPiper", "company_id": self.main_company.id}
        )
        self.env["account.chart.template"].sudo()._load_urbanpiper_fiscal_positions()
        self.assertEqual(self._shipped_position(self.main_company), existing)

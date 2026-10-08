from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import CommonPosTest


@tagged("post_install", "-at_install")
class TestPosLoyaltyProgramPricelists(CommonPosTest):
    def setUp(self):
        super().setUp()
        self.env["loyalty.program"].search([]).write({"active": False})
        self.config = self.pos_config_usd
        self.offered = self.env["product.pricelist"].create({"name": "Offered"})
        self.preset_pricelist = self.env["product.pricelist"].create(
            {"name": "Takeaway prices"}
        )
        self.unrelated = self.env["product.pricelist"].create({"name": "Unrelated"})
        preset = self.env["pos.preset"].create(
            {"name": "Takeaway", "pricelist_id": self.preset_pricelist.id}
        )
        self.config.write(
            {
                "use_pricelist": True,
                "pricelist_id": self.offered.id,
                "available_pricelist_ids": [(6, 0, self.offered.ids)],
                "use_presets": True,
                "default_preset_id": preset.id,
                "available_preset_ids": [(6, 0, preset.ids)],
            }
        )

    def _program(self, name, pricelist):
        return self.env["loyalty.program"].create(
            {
                "name": name,
                "program_type": "promotion",
                "trigger": "auto",
                "pricelist_ids": [(6, 0, pricelist.ids)],
            }
        )

    def test_program_restricted_to_a_preset_pricelist_is_loaded(self):
        on_preset = self._program("Takeaway promo", self.preset_pricelist)
        on_offered = self._program("Offered promo", self.offered)
        on_unrelated = self._program("Unrelated promo", self.unrelated)

        programs = self.config._get_program_ids()
        self.assertIn(on_preset, programs)
        self.assertIn(on_offered, programs)
        self.assertNotIn(on_unrelated, programs)

        self.config.open_ui()
        data = self.config.current_session_id.load_data(
            ["pos.config", "loyalty.program"]
        )
        loaded = {p["id"] for p in data["loyalty.program"]}
        self.assertIn(on_preset.id, loaded)
        self.assertNotIn(on_unrelated.id, loaded)

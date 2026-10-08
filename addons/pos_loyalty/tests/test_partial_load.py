from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import CommonPosTest


@tagged("post_install", "-at_install")
class TestPosLoyaltyPartialLoad(CommonPosTest):
    def test_templates_load_without_the_config(self):
        self.pos_config_usd.open_ui()
        session = self.pos_config_usd.current_session_id
        data = session.load_data(["product.template"])
        self.assertNotIn("pos.config", data)
        self.assertIn("product.template", data)

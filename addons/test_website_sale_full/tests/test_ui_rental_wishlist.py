from odoo import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale_renting.tests.common import TestWebsiteSaleRentingCommon


@tagged("-at_install", "post_install")
class TestUi(HttpCase, TestWebsiteSaleRentingCommon):
    def test_website_sale_renting_wishlist_ui(self):
        self.computer.is_published = True
        self.env.ref("base.user_admin").write(
            {
                "name": "Mitchell Admin",
                "street": "215 Vine St",
                "phone_ids": [
                    Command.create({"number": "+1 555-555-5555", "type": "landline"})
                ],
                "city": "Scranton",
                "zip": "18503",
                "country_id": self.env.ref("base.us").id,
                "state_id": self.env.ref("base.state_us_39").id,
                "email": "mitchell.admin@example.com",
            }
        )
        self.start_tour("/odoo", "shop_buy_rental_product_wishlist", login="admin")

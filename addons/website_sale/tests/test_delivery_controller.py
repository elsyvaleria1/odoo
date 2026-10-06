from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.payment.tests.common import PaymentCommon
from odoo.addons.website_sale.controllers.delivery import Delivery
from odoo.addons.website_sale.tests.common import MockRequest, WebsiteSaleCommon


@tagged("post_install", "-at_install")
class TestWebsiteSaleDeliveryController(PaymentCommon, WebsiteSaleCommon):
    def setUp(self):
        super().setUp()
        self.Controller = Delivery()

    def test_controller_change_carrier_when_transaction(self):
        website = self.website.with_env(self.env)
        self.empty_cart.transaction_ids = self._create_transaction(
            flow="redirect", state="pending"
        )
        with (
            MockRequest(
                website.env, website=website, sale_order_id=self.empty_cart.id
            ) as request,
            self.assertRaises(UserError),
        ):
            request.cart = self.empty_cart
            self.Controller.shop_set_delivery_method(dm_id=self.free_delivery.id)

    def test_controller_change_carrier_when_draft_transaction(self):
        website = self.website.with_env(self.env)
        self.empty_cart.transaction_ids = self._create_transaction(
            flow="redirect", state="draft"
        )
        with MockRequest(
            website.env, website=website, sale_order_id=self.empty_cart.id
        ):
            self.Controller.shop_set_delivery_method(dm_id=self.free_delivery.id)

    def test_available_methods(self):
        self.env["delivery.carrier"].search([]).action_archive()
        self.product_delivery_poste = self.env["product.product"].create(
            {
                "name": "The Poste",
                "type": "service",
                "categ_id": self.env.ref("delivery.product_category_deliveries").id,
                "sale_ok": False,
                "purchase_ok": False,
                "list_price": 20.0,
            }
        )
        self.env["delivery.carrier"].create(
            [
                {
                    "name": "Over 300",
                    "delivery_type": "base_on_rule",
                    "product_id": self.product_delivery_poste.id,
                    "website_published": True,
                    "price_rule_ids": [
                        Command.create(
                            {
                                "operator": ">=",
                                "max_value": 300,
                                "variable": "price",
                            }
                        ),
                    ],
                },
                {
                    "name": "Under 300",
                    "delivery_type": "base_on_rule",
                    "product_id": self.product_delivery_poste.id,
                    "website_published": True,
                    "price_rule_ids": [
                        Command.create(
                            {
                                "operator": "<",
                                "max_value": 300,
                                "variable": "price",
                            }
                        ),
                    ],
                },
                {
                    "name": "No rules",
                    "delivery_type": "base_on_rule",
                    "product_id": self.product_delivery_poste.id,
                    "website_published": True,
                },
                {
                    "name": "Fixed",
                    "product_id": self.product_delivery_poste.id,
                    "website_published": True,
                },
            ]
        )

        self.assertEqual(
            self.empty_cart._get_delivery_methods().mapped("name"),
            ["Under 300", "Fixed"],
        )


class TestPickupRadiusUnit(TransactionCase):
    def test_only_literal_one_selects_miles(self):
        config = self.env["ir.config_parameter"]
        carrier = self.env["delivery.carrier"]
        for value in (False, "", "0", "true", "True", "01", "1"):
            with self.subTest(value=value):
                config.set_param("product.volume_in_cubic_feet", value)
                expected = (
                    "uom.product_uom_mile" if value == "1" else "uom.product_uom_km"
                )
                unit = carrier._get_pickup_radius_uom()
                self.assertEqual(unit, self.env.ref(expected))
                self.assertEqual(unit._name, "uom.uom")

    def test_reloads_changed_configuration(self):
        config = self.env["ir.config_parameter"]
        for value, xmlid in (
            ("1", "uom.product_uom_mile"),
            ("0", "uom.product_uom_km"),
        ):
            config.set_param("product.volume_in_cubic_feet", value)
            self.assertEqual(
                self.env["delivery.carrier"]._get_pickup_radius_uom(),
                self.env.ref(xmlid),
            )

    def test_keeps_callers_environment(self):
        user = new_test_user(
            self.env, login="pickup_unit_reader", groups="base.group_user"
        )
        self.env["ir.config_parameter"].set_param("product.volume_in_cubic_feet", "1")
        carrier = self.env["delivery.carrier"].with_user(user)
        unit = carrier._get_pickup_radius_uom()
        self.assertEqual(unit.id, self.env.ref("uom.product_uom_mile").id)
        self.assertEqual(unit.env.uid, user.id)
        self.assertFalse(unit.env.su)

    def test_does_not_require_a_single_carrier(self):
        carrier = self.env["delivery.carrier"]
        records = carrier.new({"name": "One"}) | carrier.new({"name": "Two"})
        self.assertEqual(
            records._get_pickup_radius_uom(), carrier._get_pickup_radius_uom()
        )

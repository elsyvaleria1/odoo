from odoo import Command
from odoo.tests import tagged
from odoo.tools import SQL

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

TILL_LINES = {
    "round_per_line": [
        (20.22, 30.15),
        (6.48, 6.93),
        (4.46, 5.58),
        (27.97, 34.13),
        (0.65, 0.75),
        (0.93, 0.99),
        (0.93, 0.99),
    ],
    "round_globally": [
        (20.22, 30.15),
        (6.48, 6.93),
        (4.46, 5.58),
        (27.96, 34.13),
        (0.65, 0.75),
        (0.93, 0.99),
        (0.93, 0.99),
    ],
}


@tagged("post_install", "-at_install")
class TestPosOrderPricingTrust(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.tax15 = cls.env["account.tax"].create(
            {"name": "Trust 15%", "amount": 15, "amount_type": "percent"}
        )
        cls.product = cls.create_product(
            "Trusted Product", cls.categ_basic, 100, tax_ids=cls.tax15.ids
        )
        cls.cashier = cls.env["res.users"].create(
            {
                "name": "Restricted Cashier",
                "login": "pos_pricing_trust_cashier",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [
                    Command.link(cls.env.ref("point_of_sale.group_pos_user").id)
                ],
            }
        )

    def setUp(self):
        super().setUp()
        self._start_pos_session(self.cash_pm1, 0)

    def _sync(self, lines, paid, user=None, **order_args):
        data = self.create_ui_order_data(
            lines, pos_order_ui_args=order_args, payments=[(self.cash_pm1, paid)]
        )
        result = (
            self.env["pos.order"].with_user(user or self.cashier).sync_from_ui([data])
        )
        return self.env["pos.order"].browse(
            row["id"] for row in result["pos.order"] if row["uuid"] == data["uuid"]
        )

    def _line(self, product=None, qty=1, **values):
        return {"product": product or self.product, "quantity": qty, **values}

    def _till_engine_specs(self):
        if not hasattr(self, "_engine_products"):

            def tax(name, amount_type, amount, included, sequence, **extra):
                return self.env["account.tax"].create(
                    {
                        "name": name,
                        "amount_type": amount_type,
                        "amount": amount,
                        "price_include_override": "tax_included"
                        if included
                        else "tax_excluded",
                        "sequence": sequence,
                        **extra,
                    }
                )

            fixed = tax("Fixed 2", "fixed", 2, True, 1, include_base_amount=True)
            excl15 = tax("Excl 15", "percent", 15, False, 2)
            incl7 = tax("Incl 7", "percent", 7, True, 3)
            excl10 = tax("Excl 10", "percent", 10, False, 4)
            self._engine_products = {
                taxes: self.create_product(
                    f"Engine {index}", self.categ_basic, 1, tax_ids=taxes.ids
                )
                for index, taxes in enumerate(
                    [fixed | excl15, incl7, excl15 | excl10, incl7 | excl15, excl15]
                )
            }
        products = list(self._engine_products.values())
        specs = [
            (9.99, 3, 12.5, products[0]),
            (0.99, 7, 0, products[1]),
            (3.33, 2, 33, products[2]),
            (19.95, 1.5, 0, products[3]),
            (0.05, 13, 0, products[4]),
            (0.99, 1, 0, products[1]),
            (0.99, 1, 0, products[1]),
        ]
        return [
            self._line(
                product,
                qty,
                price_unit=price_unit,
                discount=discount,
                price_subtotal=999,
                price_subtotal_incl=999,
            )
            for price_unit, qty, discount, product in specs
        ]

    def test_stored_line_amounts_follow_the_line_not_the_till(self):
        self.config.write({"manual_discount": False, "restrict_price_control": True})
        order = self._sync(
            [
                self._line(
                    price_unit=100,
                    discount=99.99,
                    tax_ids=[Command.set([])],
                    price_subtotal=999,
                    price_subtotal_incl=999,
                )
            ],
            paid=0.01,
        )

        self.assertEqual(order.state, "paid")
        self.assertAlmostEqual(order.amount_total, 0.01)
        self.assertAlmostEqual(order.lines.price_subtotal, 0.01)
        self.assertAlmostEqual(
            order.lines.price_subtotal_incl,
            0.01,
            msg="999 means the till's amounts were stored for a 0.01 order",
        )
        self.env.flush_all()
        report = self.env["report.pos.order"].search([("order_id", "=", order.id)])
        self.assertAlmostEqual(sum(report.mapped("price_total")), 0.01)

    def test_the_server_prices_lines_as_the_till_engine_does(self):
        for method in ("round_per_line", "round_globally"):
            with self.subTest(method=method):
                self.company.tax_calculation_rounding_method = method
                order = self._sync(
                    self._till_engine_specs(), paid=79.52, user=self.env.user
                )
                self.env.invalidate_all()
                self.assertEqual(
                    [
                        (line.price_subtotal, line.price_subtotal_incl)
                        for line in order.lines.sorted("id")
                    ],
                    TILL_LINES[method],
                )
                self.assertAlmostEqual(order.amount_total, 79.52)

    def test_the_lines_of_an_order_sum_to_its_total(self):
        self.company.tax_calculation_rounding_method = "round_globally"
        order = self._sync(
            [self._line(price_unit=1.05, price_subtotal_incl=1.21)] * 3,
            paid=3.62,
            user=self.env.user,
        )

        self.env.invalidate_all()
        self.assertAlmostEqual(order.amount_total, 3.62)
        self.assertEqual(
            sorted(order.lines.mapped("price_subtotal_incl")),
            [1.2, 1.21, 1.21],
            msg="three times 1.21 is 3.63, a cent more than the order",
        )

    def test_a_server_refund_prices_its_lines_as_the_till_engine_does(self):
        self.company.tax_calculation_rounding_method = "round_globally"
        order = self._sync(self._till_engine_specs(), paid=79.52, user=self.env.user)

        refund = order._refund()

        self.env.invalidate_all()
        self.assertEqual(
            [
                (line.price_subtotal, line.price_subtotal_incl)
                for line in refund.lines.sorted("id")
            ],
            [
                (-excluded, -included)
                for excluded, included in TILL_LINES["round_globally"]
            ],
            msg="30.16 and 34.12 are the per-line compute_all of each line",
        )
        self.assertAlmostEqual(refund.amount_total, -79.52)

    def test_a_discount_a_till_does_not_allow_is_flagged(self):
        for manual_discount, flagged in ((False, True), (True, False)):
            with self.subTest(manual_discount=manual_discount):
                self.config.manual_discount = manual_discount
                order = self._sync([self._line(discount=10)], paid=103.5)

                self.assertEqual(order.state, "paid")
                self.assertEqual(order.has_pricing_breach, flagged)
                if flagged:
                    self.assertIn("does not allow", order.message_ids[0].body)

    def test_a_price_set_without_price_control_rights_is_flagged(self):
        manager = self.cashier.copy(
            {
                "login": "pos_pricing_trust_manager",
                "group_ids": [
                    Command.set(self.env.ref("point_of_sale.group_pos_manager").ids)
                ],
            }
        )
        for restrict, user, flagged in (
            (True, self.cashier, True),
            (True, manager, False),
            (False, self.cashier, False),
        ):
            with self.subTest(restrict=restrict, user=user.login):
                self.config.restrict_price_control = restrict
                order = self._sync([self._line(price_unit=90)], paid=103.5, user=user)

                self.assertEqual(order.state, "paid")
                self.assertEqual(order.has_pricing_breach, flagged)
                if flagged:
                    self.assertIn("pricelist", order.message_ids[0].body)

    def test_taxes_other_than_the_products_are_flagged(self):
        order = self._sync([self._line(tax_ids=[Command.set([])])], paid=100)

        self.assertEqual(order.state, "paid")
        self.assertTrue(order.has_pricing_breach)
        self.assertIn("taxes other than", order.message_ids[0].body)

    def test_the_pricelist_price_and_its_refund_are_not_flagged(self):
        sale = self._sync([self._line(qty=2, discount=10)], paid=207)
        self.config.write({"manual_discount": False, "restrict_price_control": True})

        refund = self._sync(
            [
                self._line(
                    qty=-1,
                    discount=10,
                    refunded_orderline_id=sale.lines.id,
                )
            ],
            paid=-103.5,
            is_refund=True,
        )

        self.assertFalse(sale.has_pricing_breach)
        self.assertEqual(refund.state, "paid")
        self.assertFalse(
            refund.has_pricing_breach,
            "a refund gives back the price and discount it was sold with",
        )

    def test_a_tip_is_priced_by_the_cashier(self):
        tip_product = self.create_product("Tip", self.categ_basic, 0)
        self.config.write(
            {"restrict_price_control": True, "tip_product_id": tip_product.id}
        )

        order = self._sync([self._line(tip_product, price_unit=7)], paid=7)

        self.assertEqual(order.state, "paid")
        self.assertFalse(order.has_pricing_breach)

    def test_the_till_loads_every_pricelist_its_rules_price_from(self):
        def pricelist(name, base=None):
            item = (
                {"base": "pricelist", "base_pricelist_id": base.id}
                if base
                else {"base": "list_price"}
            )
            return self.env["product.pricelist"].create(
                {
                    "name": name,
                    "item_ids": [
                        Command.create(
                            {
                                "applied_on": "3_global",
                                "compute_price": "percentage",
                                "percent_price": 10,
                                **item,
                            }
                        )
                    ],
                }
            )

        list_based = pricelist("List based")
        retail = pricelist("Retail", list_based)
        wholesale = pricelist("Wholesale", retail)
        # the constraint forbids a cycle, data written before it may hold one
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "UPDATE product_pricelist_item SET base = 'pricelist',"
                " base_pricelist_id = %s WHERE pricelist_id = %s",
                wholesale.id,
                list_based.id,
            )
        )
        self.env.invalidate_all()
        config = self.env["pos.config"].create(
            {
                "name": "Chained pricelists",
                "use_pricelist": True,
                "pricelist_id": wholesale.id,
                "available_pricelist_ids": [Command.set(wholesale.ids)],
            }
        )

        loaded = self.env["product.pricelist"].search(
            self.env["product.pricelist"]._load_pos_data_domain({}, config)
        )

        self.assertEqual(loaded, wholesale | retail | list_based)
        self.assertEqual(config._get_pos_pricelists(), wholesale)

from datetime import timedelta
from itertools import product

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import Form, HttpCase, TransactionCase, tagged


class TestRentalCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env.company.country_id = cls.env.ref("base.us")
        cls.env["account.tax.group"].create(
            {
                "name": "Test Account Tax Group",
                "company_ids": [Command.set(cls.env.company.ids)],
            }
        )

        cls.product_id = cls.env["product.product"].create(
            {
                "name": "Projector",
                "type": "consu",
                "rent_ok": True,
                "extra_hourly": 7.0,
                "extra_daily": 30.0,
            }
        )

        cls.product_template_id = cls.product_id.product_tmpl_id

        cls.product_template_id.product_pricing_ids.unlink()
        cls.recurrence_hourly = cls.env["sale.temporal.recurrence"].create(
            {"duration": 1.0, "unit": "hour"}
        )
        cls.recurrence_5_hours = cls.env["sale.temporal.recurrence"].create(
            {"duration": 5.0, "unit": "hour"}
        )
        cls.recurrence_15_hours = cls.env["sale.temporal.recurrence"].create(
            {"duration": 15.0, "unit": "hour"}
        )
        cls.recurrence_daily = cls.env["sale.temporal.recurrence"].create(
            {"duration": 1.0, "unit": "day"}
        )

        PRICINGS = [
            {
                "recurrence_id": cls.recurrence_hourly.id,
                "price": 3.5,
            },
            {
                "recurrence_id": cls.recurrence_5_hours.id,
                "price": 15.0,
            },
            {
                "recurrence_id": cls.recurrence_15_hours.id,
                "price": 40.0,
            },
            {
                "recurrence_id": cls.recurrence_daily.id,
                "price": 60.0,
            },
        ]

        for pricing in PRICINGS:
            pricing.update(product_template_id=cls.product_template_id.id)
            cls.env["product.pricing"].create(pricing)

        cls.tax_included = cls.env["account.tax"].create(
            {"name": "Tax Incl", "amount": 10, "price_include_override": "tax_included"}
        )
        cls.tax_excluded = cls.env["account.tax"].create(
            {"name": "Tax Excl", "amount": 10, "price_include_override": "tax_excluded"}
        )

    def test_pricing(self):
        now = fields.Datetime.now()
        self.assertEqual(
            self.product_id._get_best_pricing_rule(
                start_date=now, end_date=now + relativedelta(hours=9)
            )._get_price_for_duration(9.0, "hour"),
            30.0,
        )

        self.assertEqual(
            self.product_id._get_best_pricing_rule(
                start_date=now, end_date=now + relativedelta(hours=1)
            )._get_price_for_duration(11.0, "hour"),
            38.5,
        )

        self.assertEqual(
            self.product_id._get_best_pricing_rule(
                start_date=now, end_date=now + relativedelta(hours=16)
            )._get_price_for_duration(16.0, "hour"),
            56.0,
        )

        self.assertEqual(
            self.product_id._get_best_pricing_rule(
                start_date=now, end_date=now + relativedelta(hours=20)
            )._get_price_for_duration(20.0, "hour"),
            60.0,
        )

        self.assertEqual(
            self.product_id._get_best_pricing_rule(
                start_date=now, end_date=now + relativedelta(hours=24)
            )._get_price_for_duration(24.0, "hour"),
            60.0,
        )

    def test_pricing_advanced(self):
        return

    def test_pricelists(self):
        partner = self.env["res.partner"].create({"name": "A partner"})
        pricelist_A = self.env["product.pricelist"].create(
            {
                "name": "Pricelist A",
            }
        )
        pricelist_B = self.env["product.pricelist"].create(
            {
                "name": "Pricelist B",
            }
        )

        PRICINGS = [
            {
                "recurrence_id": self.recurrence_hourly.id,
                "price": 3.5,
                "pricelist_id": pricelist_A.id,
            },
            {
                "recurrence_id": self.recurrence_5_hours.id,
                "price": 15.0,
                "pricelist_id": pricelist_B.id,
            },
        ]
        self.product_template_id.list_price = 42
        self.product_template_id.product_pricing_ids.unlink()
        for pricing in PRICINGS:
            pricing.update(product_template_id=self.product_template_id.id)
            pricing = self.env["product.pricing"].create(pricing)

        reservation_begin = fields.Datetime.now()
        pickup_date = reservation_begin + relativedelta(days=1)
        return_date = pickup_date + relativedelta(hours=1)

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "rental_start_date": pickup_date,
                "rental_return_date": return_date,
            }
        )

        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "order_id": sale_order.id,
                "reservation_begin": reservation_begin,
            }
        )
        sol.update({"is_rental": True})

        sale_order.write({"pricelist_id": pricelist_A.id})
        sale_order._recompute_prices()
        self.assertEqual(
            sol.price_unit, 3.5, "Pricing should take into account pricelist A"
        )
        sale_order.write({"pricelist_id": pricelist_B.id})
        sale_order._recompute_prices()
        self.assertEqual(
            sol.price_unit, 15, "Pricing should take into account pricelist B"
        )
        pricelist_B.active = False
        sale_order._recompute_prices()
        self.assertEqual(
            sol.price_unit,
            42,
            "Pricing should not take into account archived pricelist B",
        )

    def test_delay_pricing(self):
        self.product_id.extra_hourly = 2.5
        self.product_id.extra_daily = 15.0

        self.assertEqual(self.product_id._get_delay_price(timedelta(hours=5.0)), 12.5)

        self.assertEqual(
            self.product_id._get_delay_price(timedelta(hours=5.0, days=6)), 102.5
        )

    def test_discount(self):
        partner = self.env["res.partner"].create({"name": "A partner"})
        pricelist_A = self.env["product.pricelist"].create(
            {
                "name": "Pricelist A",
                "company_id": self.env.company.id,
                "item_ids": [
                    (
                        0,
                        0,
                        {
                            "applied_on": "3_global",
                            "compute_price": "percentage",
                            "percent_price": 10,
                        },
                    )
                ],
            }
        )
        pricelist_B = self.env["product.pricelist"].create(
            {
                "name": "Pricelist B",
                "company_id": self.env.company.id,
                "item_ids": [
                    (
                        0,
                        0,
                        {
                            "applied_on": "3_global",
                            "compute_price": "percentage",
                            "percent_price": 20,
                        },
                    )
                ],
            }
        )

        PRICINGS = [
            {
                "recurrence_id": self.recurrence_hourly.id,
                "price": 3.5,
                "pricelist_id": pricelist_A.id,
            },
            {
                "recurrence_id": self.recurrence_5_hours.id,
                "price": 15.0,
                "pricelist_id": pricelist_B.id,
            },
        ]
        self.product_template_id.product_pricing_ids.unlink()
        for pricing in PRICINGS:
            pricing.update(product_template_id=self.product_template_id.id)
            pricing = self.env["product.pricing"].create(pricing)

        reservation_begin = fields.Datetime.now()
        pickup_date = reservation_begin + relativedelta(days=1)
        return_date = pickup_date + relativedelta(hours=1)

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "rental_start_date": pickup_date,
                "rental_return_date": return_date,
            }
        )

        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "product_qty": 1,
                "order_id": sale_order.id,
                "reservation_begin": reservation_begin,
            }
        )
        sol.update({"is_rental": True})
        sale_order.write({"pricelist_id": pricelist_A.id})
        sale_order._recompute_prices()
        self.assertEqual(
            sol.discount, 0, "Discount should always been 0 on pricelist change"
        )
        sale_order.write({"pricelist_id": pricelist_B.id})
        sale_order._recompute_prices()
        self.assertEqual(
            sol.discount, 0, "Discount should always been 0 on pricelist change"
        )

    def test_no_pickup_nor_return(self):
        partner = self.env["res.partner"].create({"name": "A partner"})
        partner.property_product_pricelist = self.env["product.pricelist"].create(
            {"name": "Test Pricelist"}
        )

        recurrence_hour = self.env["sale.temporal.recurrence"].create(
            {"duration": 1.0, "unit": "hour"}
        )
        PRICINGS = [
            {
                "recurrence_id": recurrence_hour.id,
                "price": 3.5,
            }
        ]
        self.product_template_id.product_pricing_ids.unlink()
        for pricing in PRICINGS:
            pricing.update(product_template_id=self.product_template_id.id)
            pricing = self.env["product.pricing"].create(pricing)

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
            }
        )
        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "order_id": sale_order.id,
            }
        )

        self.assertEqual(
            sol.price_unit,
            1,
            "No pricing should be taken into account if no pickup nor return date.",
        )
        sale_order._recompute_prices()
        self.assertEqual(
            sol.price_unit, 1, "Update price should not alter first computed price."
        )

    def test_no_price_update_on_pickup_return_update(self):
        partner = self.env["res.partner"].create({"name": "A partner"})
        partner.property_product_pricelist = self.env["product.pricelist"].create(
            {"name": "Test Pricelist"}
        )

        recurrence_hour = self.env["sale.temporal.recurrence"].create(
            {"duration": 1.0, "unit": "hour"}
        )
        PRICINGS = [
            {
                "recurrence_id": recurrence_hour.id,
                "price": 3.5,
            }
        ]
        self.product_template_id.product_pricing_ids.unlink()
        for pricing in PRICINGS:
            pricing.update(product_template_id=self.product_template_id.id)
            pricing = self.env["product.pricing"].create(pricing)

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
            }
        )
        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "order_id": sale_order.id,
            }
        )

        self.assertEqual(
            sol.price_unit,
            1,
            "No pricing should be taken into account if no pickup nor return date.",
        )
        sale_order.write(
            {
                "rental_start_date": fields.Datetime.now() + relativedelta(days=1),
                "rental_return_date": fields.Datetime.now()
                + relativedelta(days=1, hours=1),
            }
        )
        sol.write({"is_rental": True})
        self.assertEqual(
            sol.price_unit, 1, "Update price should not alter first computed price."
        )
        sale_order._recompute_prices()
        self.assertEqual(
            sol.price_unit, 3.5, "Update price should recompute the price."
        )

    def test_no_pricing_for_pricelist(self):
        pricelist_A = self.env["product.pricelist"].create(
            {
                "name": "Pricelist A",
            }
        )
        pricelist_B = self.env["product.pricelist"].create(
            {
                "name": "Pricelist B",
            }
        )
        partner = self.env["res.partner"].create(
            {"name": "A partner", "property_product_pricelist": pricelist_B}
        )
        recurrence_hour = self.env["sale.temporal.recurrence"].create(
            {"duration": 1.0, "unit": "hour"}
        )
        PRICINGS = [
            {
                "recurrence_id": recurrence_hour.id,
                "price": 3.5,
                "pricelist_id": pricelist_A.id,
            }
        ]
        self.product_template_id.product_pricing_ids.unlink()
        for pricing in PRICINGS:
            pricing.update(product_template_id=self.product_template_id.id)
            self.env["product.pricing"].create(pricing)

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "rental_start_date": fields.Datetime.now() + relativedelta(days=1),
                "rental_return_date": fields.Datetime.now()
                + relativedelta(days=1, hours=1),
            }
        )
        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "order_id": sale_order.id,
            }
        )
        sol.update({"is_rental": True})

        self.assertEqual(
            sol.price_unit,
            1,
            "No pricing should be taken into account if no pricing corresponds to a given pricelist.",
        )

    def test_contextual_price_is_pickup_return_dependant(self):
        pricelist_A = self.env["product.pricelist"].create(
            {
                "name": "Pricelist A",
            }
        )
        recurrence_hour = self.env["sale.temporal.recurrence"].create(
            {"duration": 1.0, "unit": "hour"}
        )
        PRICINGS = [
            {
                "recurrence_id": recurrence_hour.id,
                "price": 3.5,
            }
        ]
        self.product_template_id.product_pricing_ids.unlink()
        for pricing in PRICINGS:
            pricing.update(product_template_id=self.product_template_id.id)
            pricing = self.env["product.pricing"].create(pricing)

        price = self.product_template_id.with_context(
            start_date=fields.Datetime.now() + relativedelta(days=1),
            end_date=fields.Datetime.now() + relativedelta(days=1, hours=2),
            pricelist=pricelist_A.id,
        )._get_contextual_price()
        self.assertEqual(
            price, 7, "Contextual price should take pickup and return date into account"
        )

    def test_return_quantity_always_compliant(self):
        now = fields.Date.today()
        one_day_later = now + relativedelta(days=1)

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "A partner"}).id,
                "rental_start_date": now,
                "rental_return_date": one_day_later,
            }
        )

        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "product_qty": 5,
                "price_unit": 10,
                "order_id": sale_order.id,
                "reservation_begin": now,
            }
        )
        sol.update({"is_rental": True})

        sale_order.action_confirm()
        action_dict = sale_order.action_view_pickup()
        pickup_wizard = (
            self.env["wizard.sale.order.pickup.return"]
            .with_context(action_dict["context"])
            .create({})
        )
        pickup_wizard._update_wizard_lines()
        pickup_wizard.apply()

        action_dict = sale_order.action_view_return()
        return_wizard = (
            self.env["wizard.sale.order.pickup.return"]
            .with_context(action_dict["context"])
            .create({})
        )
        return_wizard._update_wizard_lines()
        return_wizard.rental_wizard_line_ids.qty_returned = 4
        return_wizard.apply()

        with self.assertRaises(ValidationError):
            action_dict = sale_order.action_view_return()
            return_wizard = (
                self.env["wizard.sale.order.pickup.return"]
                .with_context(action_dict["context"])
                .create({})
            )
            return_wizard._update_wizard_lines()
            return_wizard.rental_wizard_line_ids.qty_returned = 4
            return_wizard.apply()

    def test_discount_on_sol_remains(self):
        now = fields.Date.today()
        one_day_later = now + relativedelta(days=1)
        discount = 10

        partner = self.env["res.partner"].create({"name": "A partner"})
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "rental_start_date": now,
                "rental_return_date": one_day_later,
            }
        )

        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "product_qty": 1,
                "price_unit": 10,
                "order_id": sale_order.id,
                "reservation_begin": now,
                "discount": discount,
            }
        )
        sol.update({"is_rental": True})

        self.assertEqual(sol.discount, discount, "Discount should not be updated")
        sale_order.action_confirm()
        self.assertEqual(sol.discount, discount, "Discount should not be updated")
        action_dict = sale_order.action_view_pickup()
        pickup_wizard = (
            self.env["wizard.sale.order.pickup.return"]
            .with_context(action_dict["context"])
            .create({})
        )
        pickup_wizard._update_wizard_lines()
        pickup_wizard.apply()
        self.assertEqual(sol.discount, discount, "Discount should not be updated")

    def test_renting_taxes_inc2ex(self):

        fiscal_position_inc2ex = self.env["account.fiscal.position"].create(
            {"name": "inc2ex"}
        )
        self.tax_excluded.write(
            {
                "fiscal_position_ids": [Command.set(fiscal_position_inc2ex.ids)],
                "original_tax_ids": [Command.set(self.tax_included.ids)],
            }
        )
        self.product_id.taxes_id = self.tax_included

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "A partner"}).id,
                "fiscal_position_id": fiscal_position_inc2ex.id,
            }
        )

        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "order_id": sale_order.id,
            }
        )
        sol.update({"is_rental": True})
        sale_order._rental_set_dates()
        sale_order._recompute_prices()

        self.assertEqual(
            sale_order.duration_days, 1, "Default duration should be one day"
        )
        self.assertEqual(
            sale_order.remaining_hours, 0, "Default duration should be one day"
        )

        self.assertEqual(
            sol.price_total,
            sol.currency_id.round((60 / 1.1) * 1.1),
            "Price with 10% taxes should be almost equal to basic pricing (rounding difference)",
        )

    def test_renting_taxes_ex2inc(self):
        fiscal_position_ex2inc = self.env["account.fiscal.position"].create(
            {"name": "ex2inc"}
        )
        self.tax_included.write(
            {
                "fiscal_position_ids": [Command.set(fiscal_position_ex2inc.ids)],
                "original_tax_ids": [Command.set(self.tax_excluded.ids)],
            }
        )
        self.product_id.taxes_id = self.tax_excluded

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "A partner"}).id,
                "fiscal_position_id": fiscal_position_ex2inc.id,
            }
        )

        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "order_id": sale_order.id,
            }
        )
        sol.update({"is_rental": True})
        sale_order._rental_set_dates()
        sale_order._recompute_prices()

        self.assertEqual(
            sol.price_unit,
            60,
            "Price with included taxes should be equal to basic pricing(tax excluded) + 10% taxes",
        )

    def test_renting_taxes_included(self):
        self.product_id.taxes_id = self.tax_included

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "A partner"}).id,
            }
        )

        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "order_id": sale_order.id,
            }
        )
        sol.update({"is_rental": True})
        sale_order._rental_set_dates()
        sale_order._recompute_prices()
        self.assertEqual(
            sol.price_total,
            60.0,
            "Price should be equal to basic pricing (10% tax included)",
        )

    def test_renting_taxes_excluded(self):
        self.product_id.taxes_id = self.tax_excluded

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "A partner"}).id,
            }
        )

        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "order_id": sale_order.id,
            }
        )
        sol.update({"is_rental": True})
        sale_order._rental_set_dates()
        sale_order._recompute_prices()

        self.assertEqual(
            sol.price_total,
            sol.currency_id.round(60 * 1.1),
            "Price should be equal to basic pricing + 10% tax",
        )

    def test_renting_taxes_ex_inc(self):
        self.product_id.taxes_id = self.tax_excluded + self.tax_included
        self.tax_included.include_base_amount = True
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "A partner"}).id,
            }
        )

        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "order_id": sale_order.id,
            }
        )
        sol.update({"is_rental": True})
        sale_order._rental_set_dates()
        sale_order._recompute_prices()

        self.assertEqual(
            sol.price_total,
            60 * 1.1,
            "Price should be equal to basic pricing (tax included) + 10% (tax excluded)",
        )

    def test_renting_taxes_included_multicompany(self):

        company2 = self.env["res.company"].create({"name": "Company 2"})
        self.tax_included.company_ids = company2

        self.product_id.taxes_id = self.tax_included

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "A partner"}).id,
            }
        )

        sol = self.env["sale.order.line"].create(
            {
                "product_id": self.product_id.id,
                "order_id": sale_order.id,
            }
        )
        sol.update({"is_rental": True})
        sale_order._rental_set_dates()
        sale_order._recompute_prices()

        self.assertEqual(
            sol.price_total,
            60,
            "Included tax related to another company should not apply",
        )

    def test_non_rental_line_does_not_change_description(self):
        water_bottle = self.env["product.product"].create(
            {
                "name": "Water Bottle",
            }
        )
        will_smith = self.env["res.partner"].create(
            {
                "name": "Will Smith",
            }
        )

        now = fields.Datetime.now()
        order = self.env["sale.order"].create(
            {
                "partner_id": will_smith.id,
                "rental_start_date": now,
                "rental_return_date": now + timedelta(days=2),
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_id.id,
                        }
                    ),
                    Command.create({"product_id": water_bottle.id}),
                ],
            }
        )
        rental_order_line, non_rental_order_line = order.line_ids
        rental_order_line.is_rental = True
        self.assertTrue(order.is_rental_order)

        non_rental_order_line.name = "My Water Bottle"

        order.rental_start_date = now + timedelta(days=1)

        self.assertEqual(non_rental_order_line.name, "My Water Bottle")

    def test_rental_line_change_description_onchange_duration(self):
        partner = self.env["res.partner"].create({"name": "A partner"})
        product = self.env["product.product"].create(
            {
                "name": "Product A",
            }
        )

        now = fields.Datetime.now()
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "rental_start_date": now,
                "rental_return_date": now + timedelta(days=2),
            }
        )
        order_line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_qty": 1,
                "is_rental": True,
            }
        )
        old_description = order_line.name
        with Form(order) as order_form:
            order_form.rental_start_date = now
            order_form.rental_return_date = now + timedelta(days=3)

        new_description = order_line.name

        self.assertNotEqual(
            old_description,
            new_description,
            "order line name for rental order_line should change on change of rental duration on"
            " sale order form",
        )

    def test_copy_product_variant_pricings(self):
        product = self.product_template_id.with_context(create_product_product=True)
        product.product_pricing_ids.unlink()
        product_attributes = self.env["product.attribute"].create(
            [
                {
                    "name": attribute_name,
                    "value_ids": [
                        Command.create({"name": name}) for name in value_names
                    ],
                }
                for attribute_name, value_names in (
                    ("Color", ("Blue", "Red")),
                    ("Size", ("S", "M")),
                )
            ]
        )
        product.attribute_line_ids = [
            Command.create(
                {
                    "attribute_id": product_attribute.id,
                    "value_ids": product_attribute.value_ids.ids,
                }
            )
            for product_attribute in product_attributes
        ]
        for i, variant in enumerate(product.product_variant_ids, start=1):
            self.env["product.pricing"].create(
                [
                    {
                        "product_template_id": product.id,
                        "product_variant_ids": [Command.link(variant.id)],
                        "recurrence_id": self.recurrence_hourly.id,
                        "price": 10.0 * i,
                        "pricelist_id": self.env["product.pricelist"]
                        .create({"name": f"list {i}"})
                        .id,
                    },
                    {
                        "product_template_id": product.id,
                        "product_variant_ids": [Command.link(variant.id)],
                        "recurrence_id": self.recurrence_daily.id,
                        "price": 25.0 * i,
                    },
                ]
            )
        pricings_1 = product.product_pricing_ids.sorted()
        pricings_2 = product.copy().product_pricing_ids.sorted()
        self.assertEqual(
            len(pricings_2),
            8,
            "copied product should get 8 pricings",
        )
        self.assertNotEqual(
            pricings_2.product_variant_ids,
            pricings_1.product_variant_ids,
            "copied pricings shouldn't be linked to the original products",
        )
        for pricing_1, pricing_2 in zip(pricings_1, pricings_2, strict=True):
            self.assertEqual(pricing_2.price, pricing_1.price)
            self.assertEqual(pricing_2.recurrence_id, pricing_1.recurrence_id)
            self.assertEqual(pricing_2.pricelist_id, pricing_1.pricelist_id)

    def test_copy_rental_status(self):
        partner = self.env["res.partner"].create({"name": "A partner"})
        now = self.env.cr.now()
        pickup_date = now + relativedelta(days=1)
        return_date = pickup_date + relativedelta(hours=1)

        sale_order = (
            self.env["sale.order"]
            .with_context(in_rental_app=True)
            .create(
                {
                    "partner_id": partner.id,
                    "rental_start_date": pickup_date,
                    "rental_return_date": return_date,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_id.id,
                                "is_rental": True,
                            }
                        ),
                        Command.create(
                            {
                                "product_id": self.product_id.id,
                                "is_rental": False,
                            }
                        ),
                    ],
                }
            )
        )

        sol_rent = sale_order.line_ids.filtered("is_rental")
        sol_buy = sale_order.line_ids - sol_rent

        dupe_order = sale_order.copy()
        self.assertEqual(dupe_order.rental_status, "draft")
        self.assertEqual(dupe_order.line_ids[0].is_rental, sol_rent.is_rental)
        self.assertEqual(dupe_order.line_ids[1].is_rental, sol_buy.is_rental)

    def test_a_sent_rental_quotation_is_in_sent_status(self):
        partner = self.env["res.partner"].create({"name": "A partner"})
        pickup_date = self.env.cr.now() + relativedelta(days=1)
        sale_order = (
            self.env["sale.order"]
            .with_context(in_rental_app=True)
            .create(
                {
                    "partner_id": partner.id,
                    "rental_start_date": pickup_date,
                    "rental_return_date": pickup_date + relativedelta(hours=1),
                    "line_ids": [
                        Command.create(
                            {"product_id": self.product_id.id, "is_rental": True}
                        ),
                    ],
                }
            )
        )
        self.assertEqual(sale_order.rental_status, "draft")
        sale_order.action_quotation_sent()
        self.assertEqual(sale_order.rental_status, "sent")
        sale_order.action_confirm()
        self.assertEqual(sale_order.rental_status, "pickup")

    def test_product_display_price(self):
        product = self.env["product.template"].with_context(default_rent_ok=True)
        changes = product.onchange(
            {},
            [],
            {
                "display_price": {},
                "currency_id": {},
            },
        )
        self.assertEqual(changes["value"]["display_price"], "$\xa01.00 (fixed)")


@tagged("post_install", "-at_install")
class TestUi(HttpCase):
    def test_rental_flow(self):
        self.env.ref("base.user_admin").write(
            {
                "email": "mitchell.admin@example.com",
            }
        )

        self.env["res.partner"].name_create("Agrolait")
        self.start_tour("/odoo", "rental_tour", login="admin")

    def test_product_displayed_on_rental_only(self):

        self.env["product.product"].create(
            [
                {
                    "name": f"product:{sale_ok=},{rent_ok=}",
                    "type": "consu",
                    "rent_ok": rent_ok,
                    "sale_ok": sale_ok,
                }
                for sale_ok, rent_ok in product([True, False], [False, True])
            ]
        )

        self.start_tour("/odoo", "sale_renting_product_display", login="admin")
        self.start_tour("/odoo", "sale_product_display", login="admin")

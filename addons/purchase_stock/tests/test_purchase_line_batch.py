from datetime import timedelta

from odoo import Command, fields
from odoo.tests import tagged

from .common import PurchaseTestCommon

LINE_FIELDS = (
    "name",
    "product_qty",
    "product_uom_id",
    "price_unit",
    "discount",
    "tax_ids",
    "date_commitment",
)


@tagged("post_install", "-at_install")
class TestPurchaseLinePreparationBatch(PurchaseTestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("fr_FR")
        today = fields.Date.context_today(cls.env.user)
        cls.uom_dozen = cls.env.ref("uom.product_uom_dozen")
        cls.vendor.lang = "en_US"
        cls.vendor_fr = cls.env["res.partner"].create(
            {"name": "Fournisseur", "lang": "fr_FR", "is_company": True},
        )
        cls.contact_fr = cls.env["res.partner"].create(
            {"name": "Contact", "lang": "fr_FR", "parent_id": cls.vendor_fr.id},
        )
        cls.tax = cls.env["account.tax"].create(
            {"name": "Batch purchase 7", "amount": 7, "type_tax_use": "purchase"},
        )

        Attribute = cls.env["product.attribute"]
        color = Attribute.create(
            {
                "name": "Batch color",
                "value_ids": [Command.create({"name": n}) for n in ("Red", "Blue")],
            },
        )
        color.value_ids[0].with_context(lang="fr_FR").name = "Rouge"
        color.value_ids[1].with_context(lang="fr_FR").name = "Bleu"
        material = Attribute.create(
            {
                "name": "Batch material",
                "value_ids": [Command.create({"name": "Steel"})],
            },
        )
        engraving = Attribute.create(
            {
                "name": "Batch engraving",
                "create_variant": "no_variant",
                "value_ids": [Command.create({"name": n}) for n in ("Yes", "No")],
            },
        )

        def attribute_line(attribute):
            return Command.create(
                {
                    "attribute_id": attribute.id,
                    "value_ids": [Command.set(attribute.value_ids.ids)],
                },
            )

        Template = cls.env["product.template"]
        common = {
            "is_storable": True,
            "purchase_ok": True,
            "route_ids": [Command.link(cls.route_buy.id)],
        }
        cls.widget = Template.create(
            {
                **common,
                "name": "Widget",
                "description_purchase": "Buy the widget",
                "supplier_taxes_id": [Command.set(cls.tax.ids)],
                "standard_price": 2.0,
                "attribute_line_ids": [
                    attribute_line(color),
                    attribute_line(material),
                    attribute_line(engraving),
                ],
            },
        )
        cls.widget.with_context(lang="fr_FR").write(
            {"name": "Bidule", "description_purchase": "Acheter le bidule"},
        )
        cls.gadget = Template.create(
            {**common, "name": "Gadget", "default_code": "G1", "standard_price": 9.5},
        )
        cls.gizmo = Template.create(
            {
                **common,
                "name": "Gizmo",
                "standard_price": 7.25,
                "description_purchase": "No vendor at all",
            },
        )
        cls.thing = Template.create(
            {
                **common,
                "name": "Thing",
                "standard_price": 1.0,
                "attribute_line_ids": [attribute_line(color)],
            },
        )
        for prefix, template in (("W", cls.widget), ("T", cls.thing)):
            for index, variant in enumerate(template.product_variant_ids):
                variant.default_code = f"{prefix}{index}"
        red_thing = cls.thing.product_variant_ids[0]

        cls.env["product.supplierinfo"].create(
            [
                {
                    "partner_id": cls.vendor.id,
                    "product_tmpl_id": cls.widget.id,
                    "price": 10.0,
                    "product_name": "EN widget",
                    "product_code": "EW",
                },
                {
                    "partner_id": cls.vendor.id,
                    "product_tmpl_id": cls.widget.id,
                    "price": 8.0,
                    "min_qty": 10,
                },
                {
                    "partner_id": cls.vendor_fr.id,
                    "product_tmpl_id": cls.widget.id,
                    "price": 12.0,
                    "product_name": "Bidule futur",
                    "date_start": today + timedelta(days=30),
                },
                {
                    "partner_id": cls.vendor_fr.id,
                    "product_tmpl_id": cls.widget.id,
                    "price": 13.0,
                },
                {
                    "partner_id": cls.vendor.id,
                    "product_tmpl_id": cls.gadget.id,
                    "price": 100.0,
                    "product_uom_id": cls.uom_dozen.id,
                },
                {
                    "partner_id": cls.vendor_fr.id,
                    "product_tmpl_id": cls.gadget.id,
                    "price": 5.0,
                    "product_code": "GOLD",
                    "date_end": today - timedelta(days=3),
                },
                {
                    "partner_id": cls.vendor_fr.id,
                    "product_tmpl_id": cls.gadget.id,
                    "price": 6.0,
                    "product_code": "GFR",
                    "discount": 10,
                },
                {
                    "partner_id": cls.vendor.id,
                    "product_tmpl_id": cls.thing.id,
                    "product_id": red_thing.id,
                    "price": 3.0,
                    "product_name": "Red thing",
                },
                {
                    "partner_id": cls.vendor.id,
                    "product_tmpl_id": cls.thing.id,
                    "price": 4.0,
                    "product_code": "TT",
                },
                {
                    "partner_id": cls.vendor_fr.id,
                    "product_tmpl_id": cls.thing.id,
                    "price": 4.5,
                    "min_qty": 5,
                    "product_name": "Chose",
                },
            ],
        )
        cls.product_ids = (
            cls.widget | cls.gadget | cls.gizmo | cls.thing
        ).product_variant_ids.ids

    def _prepare(self, product, quantity, uom, partner, order):
        return self.env["purchase.order.line"]._prepare_purchase_order_line(
            product,
            quantity,
            uom,
            self.env.company,
            partner,
            order,
        )

    def _comparable(self, vals):
        return {name: vals[name] for name in LINE_FIELDS}

    def test_batch_lines_equal_the_lines_built_one_product_at_a_time(self):
        names = set()
        for partner in (self.vendor, self.contact_fr):
            order = self.env["purchase.order"].create({"partner_id": partner.id})
            for quantity in (1, 12):
                for uom in (self.uom, self.uom_dozen):
                    self.env.invalidate_all()
                    batch = {
                        product.id: self._prepare(
                            product, quantity, uom, partner, order
                        )
                        for product in self.env["product.product"].browse(
                            self.product_ids,
                        )
                    }
                    for product_id, vals in batch.items():
                        self.env.invalidate_all()
                        alone = self._prepare(
                            self.env["product.product"].browse(product_id),
                            quantity,
                            uom,
                            partner,
                            order,
                        )
                        self.assertEqual(
                            self._comparable(vals),
                            self._comparable(alone),
                        )
                        names.add(vals["name"])
        self.assertLessEqual(
            {
                "[EW] EN widget (Red)\nBuy the widget",
                "[W0] Widget (Red)\nBuy the widget",
                "[W1] Bidule (Bleu)\nAcheter le bidule",
                "[T0] Red thing (Red)",
                "[TT] Thing (Blue)",
                "[T1] Chose (Bleu)",
                "[GFR] Gadget",
                "[G1] Gadget",
                "Gizmo\nNo vendor at all",
            },
            names,
        )

    def test_procured_lines_equal_the_lines_built_one_product_at_a_time(self):
        date_planned = fields.Datetime.now() + timedelta(days=10)
        products = self.env["product.product"].browse(self.product_ids)
        buyable = products.filtered(lambda p: p.product_tmpl_id != self.gizmo)
        self.env.invalidate_all()
        self.env["stock.rule"].run(
            [
                self.env["stock.rule"].Procurement(
                    product,
                    2.0,
                    product.uom_id,
                    self.warehouse.lot_stock_id,
                    product.name,
                    "batch",
                    self.env.company,
                    {"warehouse_id": self.warehouse, "date_planned": date_planned},
                )
                for product in self.env["product.product"].browse(buyable.ids)
            ],
        )
        lines = self.env["purchase.order.line"].search(
            [("product_id", "in", buyable.ids)],
        )
        self.assertEqual(lines.product_id, buyable)
        for line in lines:
            self.env.invalidate_all()
            alone = self._prepare(
                self.env["product.product"].browse(line.product_id.id),
                line.product_qty,
                line.product_uom_id,
                line.partner_id,
                line.order_id,
            )
            self.assertEqual(line.name, alone["name"])
            self.assertEqual(line.price_unit, alone["price_unit"])
            self.assertEqual(line.discount, alone["discount"])
            self.assertEqual(line.tax_ids.ids, alone["tax_ids"][0][2])
            self.assertEqual(line.product_uom_id.id, alone["product_uom_id"])
        self.assertEqual(
            sorted(lines.mapped("name")),
            [
                "[EW] EN widget (Blue)\nBuy the widget",
                "[EW] EN widget (Red)\nBuy the widget",
                "[GFR] Gadget",
                "[T0] Red thing (Red)",
                "[TT] Thing (Blue)",
            ],
        )

    def test_line_preparation_costs_no_query_per_product(self):
        def prepare(count):
            products = self.env["product.product"].browse(products_ids[:count])
            for product in products:
                self._prepare(product, 3, product.uom_id, self.vendor_fr, order)

        products = self.env["product.product"].create(
            [
                {
                    "name": f"Batch product {index}",
                    "default_code": f"B{index}",
                    "purchase_ok": True,
                }
                for index in range(12)
            ],
        )
        products_ids = products.ids
        self.env["product.supplierinfo"].create(
            [
                {
                    "partner_id": self.vendor_fr.id,
                    "product_tmpl_id": product.product_tmpl_id.id,
                    "price": 1.0 + index,
                    "product_code": f"V{index}" if index % 3 else False,
                }
                for index, product in enumerate(products)
                if index % 2
            ],
        )
        order = self.env["purchase.order"].create({"partner_id": self.vendor_fr.id})
        self.assertQueriesConstant(prepare, small=2, large=12)

    def test_suggest_costs_no_query_per_suggested_product(self):
        def suggest(count):
            order = self.env["purchase.order"].create({"partner_id": self.vendor.id})
            order.with_context(
                suggest_based_on="actual_demand",
                suggest_percent=100,
                warehouse_id=self.warehouse.id,
                suggest_domain=[("id", "in", products_ids[:count])],
            ).action_purchase_order_suggest()
            self.assertEqual(len(order.line_ids), count)

        products = self.env["product.product"].create(
            [
                {
                    "name": f"Suggested product {index}",
                    "is_storable": True,
                    "purchase_ok": True,
                }
                for index in range(10)
            ],
        )
        products_ids = products.ids
        self.env["product.supplierinfo"].create(
            [
                {
                    "partner_id": self.vendor.id,
                    "product_tmpl_id": product.product_tmpl_id.id,
                    "price": 2.0,
                }
                for product in products[::2]
            ],
        )
        for product in products:
            self.env["stock.quant"]._update_available_quantity(
                product,
                self.warehouse.lot_stock_id,
                -8,
            )
        self.assertQueriesConstant(suggest, small=2, large=10)

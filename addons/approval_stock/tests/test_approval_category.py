from lxml import etree

from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval_product.tests.common import create_test_product


class TestApprovalCategoryStock(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)],
            limit=1,
        )
        cls.picking_type = cls.warehouse.int_type_id
        cls.picking_type.active = True
        cls.picking_type.active = True

        cls.location_src = cls.env["stock.location"].create(
            {
                "name": "Test Source Location",
                "usage": "internal",
                "company_id": cls.company.id,
            },
        )
        cls.location_dest = cls.env["stock.location"].create(
            {
                "name": "Test Destination Location",
                "usage": "internal",
                "company_id": cls.company.id,
            },
        )

        cls.product_categ = cls.env["product.category"].create(
            {
                "name": "Test Category for Stock Approval",
            },
        )

        cls.product = create_test_product(
            cls.env,
            name="Test Product",
            type="consu",
            is_storable=True,
            categ_id=cls.product_categ.id,
        )

    def test_create_stock_approval_category(self):
        category = self.env["approval.category"].create(
            {
                "name": "Stock Transfer Approval (test)",
                "approval_type": "stock",
                "company_id": self.company.id,
            },
        )

        self.assertEqual(category.approval_type, "stock")
        self.assertEqual(category.company_id, self.company)

    def test_stock_approval_mode_selection(self):
        category = self.env["approval.category"].create(
            {
                "name": "Stock Approval Mode Test",
                "approval_type": "stock",
                "stock_approval_mode": "picking_type",
                "company_id": self.company.id,
            },
        )

        self.assertEqual(category.stock_approval_mode, "picking_type")

        category.stock_approval_mode = "location"
        self.assertEqual(category.stock_approval_mode, "location")

        category.stock_approval_mode = "product"
        self.assertEqual(category.stock_approval_mode, "product")

        category.stock_approval_mode = "combined"
        self.assertEqual(category.stock_approval_mode, "combined")

    def test_picking_type_restriction(self):
        category = self.env["approval.category"].create(
            {
                "name": "Picking Type Restricted",
                "approval_type": "stock",
                "picking_type_ids": [Command.link(self.picking_type.id)],
                "company_id": self.company.id,
            },
        )

        self.assertIn(self.picking_type, category.picking_type_ids)

    def test_location_restriction(self):
        category = self.env["approval.category"].create(
            {
                "name": "Location Restricted",
                "approval_type": "stock",
                "location_ids": [Command.link(self.location_src.id)],
                "company_id": self.company.id,
            },
        )

        self.assertIn(self.location_src, category.location_ids)

    def test_product_category_restriction(self):
        category = self.env["approval.category"].create(
            {
                "name": "Product Category Restricted",
                "approval_type": "stock",
                "stock_product_categ_ids": [Command.link(self.product_categ.id)],
                "company_id": self.company.id,
            },
        )

        self.assertIn(self.product_categ, category.stock_product_categ_ids)

    def test_applies_to_picking_matching_picking_type(self):
        category = self.env["approval.category"].create(
            {
                "name": "Picking Type Check",
                "approval_type": "stock",
                "picking_type_ids": [Command.link(self.picking_type.id)],
                "company_id": self.company.id,
            },
        )

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
            },
        )

        self.assertTrue(category._is_applicable_for(picking))

    def test_applies_to_picking_matching_location(self):
        category = self.env["approval.category"].create(
            {
                "name": "Location Check",
                "approval_type": "stock",
                "location_ids": [Command.link(self.location_src.id)],
                "company_id": self.company.id,
            },
        )

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
            },
        )

        self.assertTrue(category._is_applicable_for(picking))

    def test_does_not_apply_to_unmatched_picking(self):
        other_location = self.env["stock.location"].create(
            {
                "name": "Other Location",
                "usage": "internal",
                "company_id": self.company.id,
            },
        )

        category = self.env["approval.category"].create(
            {
                "name": "Other Location Check",
                "approval_type": "stock",
                "location_ids": [Command.link(other_location.id)],
                "company_id": self.company.id,
            },
        )

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
            },
        )

        self.assertFalse(category._is_applicable_for(picking))

    def test_onchange_approval_type_stock(self):
        category = self.env["approval.category"].new(
            {
                "name": "Stock Onchange Test",
                "approval_type": "stock",
            },
        )
        category._onchange_approval_type()

        self.assertEqual(category.has_date, "optional")
        self.assertEqual(category.has_reference, "optional")

    def test_onchange_approval_type_asset_log(self):
        category = self.env["approval.category"].new(
            {
                "name": "Asset Log Onchange Test",
                "approval_type": "asset_log",
            },
        )
        category._onchange_approval_type()

        self.assertEqual(category.has_date, "required")
        self.assertEqual(category.has_asset, "required")
        self.assertEqual(category.has_odometer, "required")

    def test_switching_away_from_asset_log_clears_its_requirements(self):
        category = self.env["approval.category"].new(
            {
                "name": "Type Switch Test",
                "approval_type": "asset_log",
            },
        )
        category._onchange_approval_type()

        category.approval_type = "stock"
        category._onchange_approval_type()

        self.assertEqual(
            (category.has_asset, category.has_odometer),
            ("no", "no"),
            "the onchange has to be total, not additive: a stock request must "
            "not inherit the asset log's demand for a vehicle and a reading",
        )

    def test_the_approval_mode_is_never_empty(self):
        category = self.env["approval.category"].create(
            {
                "name": "Mode Default Test",
                "approval_type": "stock",
            },
        )

        self.assertEqual(category.stock_approval_mode, "combined")
        self.assertEqual(
            category._get_approval_mode_hidden_criteria(),
            (),
            "an empty mode hides — and the onchange then clears — all three "
            "criterion fields at once",
        )


class TestApprovalCategoryProductCategoryRestriction(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)],
            limit=1,
        )
        cls.picking_type = cls.warehouse.int_type_id
        cls.picking_type.active = True

        cls.location_src = cls.warehouse.lot_stock_id
        cls.location_dest = cls.env["stock.location"].create(
            {
                "name": "Test Dest",
                "usage": "internal",
                "company_id": cls.company.id,
            },
        )

        cls.restricted_categ = cls.env["product.category"].create(
            {
                "name": "Restricted Category",
            },
        )
        cls.normal_categ = cls.env["product.category"].create(
            {
                "name": "Normal Category",
            },
        )

        cls.restricted_product = create_test_product(
            cls.env,
            name="Restricted Product",
            type="consu",
            is_storable=True,
            categ_id=cls.restricted_categ.id,
        )
        cls.normal_product = create_test_product(
            cls.env,
            name="Normal Product",
            type="consu",
            is_storable=True,
            categ_id=cls.normal_categ.id,
        )

    def test_is_applicable_with_product_category_match(self):
        category = self.env["approval.category"].create(
            {
                "name": "Product Category Check",
                "approval_type": "stock",
                "stock_product_categ_ids": [Command.link(self.restricted_categ.id)],
                "company_id": self.company.id,
            },
        )

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.restricted_product.id,
                            "product_uom_qty": 1.0,
                            "product_uom_id": self.restricted_product.uom_id.id,
                            "location_id": self.location_src.id,
                            "location_dest_id": self.location_dest.id,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(category._is_applicable_for(picking))

    def test_is_applicable_with_product_category_no_match(self):
        category = self.env["approval.category"].create(
            {
                "name": "Product Category No Match",
                "approval_type": "stock",
                "stock_product_categ_ids": [Command.link(self.restricted_categ.id)],
                "company_id": self.company.id,
            },
        )

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.normal_product.id,
                            "product_uom_qty": 1.0,
                            "product_uom_id": self.normal_product.uom_id.id,
                            "location_id": self.location_src.id,
                            "location_dest_id": self.location_dest.id,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(category._is_applicable_for(picking))


@tagged("post_install", "-at_install")
class TestApprovalCategoryFormVisibility(TransactionCase):
    def _invisible_chain(self, arch, field_name):
        node = arch.xpath(f"//field[@name='{field_name}']")[0]
        chain = []
        while node is not None:
            condition = node.get("invisible")
            if condition:
                chain.append(condition)
            node = node.getparent()
        return chain

    def test_the_asset_requirements_are_gated_on_the_asset_log_type(self):
        arch = etree.fromstring(
            self.env["approval.category"]
            .get_view(
                self.env.ref("approval.view_approval_category_form").id,
                "form",
            )["arch"]
            .encode(),
        )

        for field_name in ("has_asset", "has_odometer"):
            self.assertIn(
                "approval_type != 'asset_log'",
                self._invisible_chain(arch, field_name),
                f"{field_name} only means something for an asset log, but it "
                f"rendered on every approval category form",
            )

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestPurchaseOrderCreation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.vendor_a = cls.env["res.partner"].create(
            {
                "name": "Vendor A",
                "supplier_rank": 1,
            },
        )

        cls.vendor_b = cls.env["res.partner"].create(
            {
                "name": "Vendor B",
                "supplier_rank": 1,
            },
        )

        cls.product_a1 = cls.env["product.product"].create(
            {
                "name": "Product A1",
                "type": "consu",
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.vendor_a.id,
                            "min_qty": 1.0,
                            "price": 100.0,
                        },
                    ),
                ],
            },
        )

        cls.product_a2 = cls.env["product.product"].create(
            {
                "name": "Product A2",
                "type": "consu",
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.vendor_a.id,
                            "min_qty": 1.0,
                            "price": 150.0,
                        },
                    ),
                ],
            },
        )

        cls.product_b1 = cls.env["product.product"].create(
            {
                "name": "Product B1",
                "type": "consu",
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.vendor_b.id,
                            "min_qty": 1.0,
                            "price": 200.0,
                        },
                    ),
                ],
            },
        )

        cls.product_no_vendor = cls.env["product.product"].create(
            {
                "name": "Product Without Vendor",
                "type": "consu",
            },
        )

        cls.approver = cls.env["res.users"].create(
            {
                "name": "Approver",
                "login": "approver_po_creation",
                "group_ids": [
                    (6, 0, [cls.env.ref("purchase.group_purchase_manager").id]),
                ],
            },
        )

        cls.category = cls.env["approval.category"].create(
            {
                "name": "Purchase Request",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )

        add_category_approver(cls.category, cls.approver, required=True)

    def test_create_single_po_from_single_vendor_lines(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Single Vendor Request",
                "category_id": self.category.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a1.id,
                            "quantity": 10.0,
                            "price_unit": 100.0,
                            "product_uom_id": self.product_a1.uom_id.id,
                            "description": "Product A1",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a2.id,
                            "quantity": 5.0,
                            "price_unit": 150.0,
                            "product_uom_id": self.product_a2.uom_id.id,
                            "description": "Product A2",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_purchase_orders()

        pos = approval.line_ids.mapped("purchase_order_line_id.order_id")
        self.assertEqual(len(pos), 1, "Should create ONE PO for single vendor")

        po = pos[0]
        self.assertEqual(po.partner_id, self.vendor_a, "PO has correct vendor")
        self.assertEqual(len(po.line_ids), 2, "PO has both lines")

        lines = po.line_ids.sorted(lambda line: line.product_id.id)
        self.assertEqual(lines[0].product_id, self.product_a1)
        self.assertEqual(lines[0].product_qty, 10.0)
        self.assertEqual(lines[1].product_id, self.product_a2)
        self.assertEqual(lines[1].product_qty, 5.0)

    def test_create_multiple_pos_for_multiple_vendors(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Multi Vendor Request",
                "category_id": self.category.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a1.id,
                            "quantity": 10.0,
                            "price_unit": 100.0,
                            "product_uom_id": self.product_a1.uom_id.id,
                            "description": "Product A1",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a2.id,
                            "quantity": 5.0,
                            "price_unit": 150.0,
                            "product_uom_id": self.product_a2.uom_id.id,
                            "description": "Product A2",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_b1.id,
                            "quantity": 3.0,
                            "price_unit": 200.0,
                            "product_uom_id": self.product_b1.uom_id.id,
                            "description": "Product B1",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_purchase_orders()

        pos = approval.line_ids.mapped("purchase_order_line_id.order_id")
        self.assertEqual(len(pos), 2, "Should create TWO POs for two vendors")

        po_a = pos.filtered(lambda p: p.partner_id == self.vendor_a)
        self.assertTrue(po_a, "PO for Vendor A created")
        self.assertEqual(len(po_a.line_ids), 2, "Vendor A PO has 2 lines")

        po_b = pos.filtered(lambda p: p.partner_id == self.vendor_b)
        self.assertTrue(po_b, "PO for Vendor B created")
        self.assertEqual(len(po_b.line_ids), 1, "Vendor B PO has 1 line")

    def test_error_when_product_has_no_vendor(self):
        approval = self.env["approval.request"].create(
            {
                "name": "No Vendor Product Request",
                "category_id": self.category.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_no_vendor.id,
                            "quantity": 10.0,
                            "price_unit": 100.0,
                            "product_uom_id": self.product_no_vendor.uom_id.id,
                            "description": "Product Without Vendor",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()

        with self.assertRaises(UserError) as cm:
            approval.action_create_purchase_orders()

        self.assertIn("vendor", str(cm.exception).lower())

    def test_approval_lines_linked_to_po_lines(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Link Test Request",
                "category_id": self.category.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a1.id,
                            "quantity": 10.0,
                            "price_unit": 100.0,
                            "product_uom_id": self.product_a1.uom_id.id,
                            "description": "Product A1",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a2.id,
                            "quantity": 5.0,
                            "price_unit": 150.0,
                            "product_uom_id": self.product_a2.uom_id.id,
                            "description": "Product A2",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_purchase_orders()

        for line in approval.line_ids:
            self.assertTrue(
                line.purchase_order_line_id,
                f"Approval line for {line.product_id.name} should be linked to PO line",
            )
            self.assertEqual(
                line.purchase_order_line_id.product_id,
                line.product_id,
                "Linked PO line has correct product",
            )

    def test_po_origin_set_to_approval_name(self):
        approval = self.env["approval.request"].create(
            {
                "name": "PR-2025-001",
                "category_id": self.category.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a1.id,
                            "quantity": 10.0,
                            "price_unit": 100.0,
                            "product_uom_id": self.product_a1.uom_id.id,
                            "description": "Product A1",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_purchase_orders()

        po = approval.line_ids.purchase_order_line_id.order_id
        self.assertEqual(
            po.origin,
            "PR-2025-001",
            "PO origin should be approval request name",
        )

    def test_count_purchase_orders_includes_both_sources(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Count Test Request",
                "category_id": self.category.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a1.id,
                            "quantity": 10.0,
                            "price_unit": 100.0,
                            "product_uom_id": self.product_a1.uom_id.id,
                            "description": "Product A1",
                        },
                    ),
                ],
            },
        )

        self.assertEqual(approval.count_purchase_order, 0)

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_purchase_orders()

        self.assertEqual(
            approval.count_purchase_order,
            1,
            "Should count PO from creation flow",
        )

        po = approval.line_ids.purchase_order_line_id.order_id
        self.assertEqual(
            po.approval_request_id,
            approval,
            "PO linked to approval request",
        )

    def test_manual_seller_id_used_over_auto_select(self):
        vendor_alt = self.env["res.partner"].create(
            {
                "name": "Alternative Vendor",
                "supplier_rank": 1,
            },
        )
        alt_seller = self.env["product.supplierinfo"].create(
            {
                "partner_id": vendor_alt.id,
                "product_tmpl_id": self.product_a1.product_tmpl_id.id,
                "min_qty": 1.0,
                "price": 200.0,
            },
        )

        approval = self.env["approval.request"].create(
            {
                "name": "Manual Vendor Request",
                "category_id": self.category.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a1.id,
                            "quantity": 10.0,
                            "price_unit": 100.0,
                            "product_uom_id": self.product_a1.uom_id.id,
                            "description": "Product A1",
                            "seller_id": alt_seller.id,
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()
        approval.action_create_purchase_orders()

        po = approval.line_ids.purchase_order_line_id.order_id
        self.assertEqual(
            po.partner_id,
            vendor_alt,
            "PO should use manually selected vendor, not auto-selected one",
        )


@tagged("post_install", "-at_install")
class TestPurchaseOrderCreationVendorUom(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.uom_dozen = cls.env.ref("uom.product_uom_dozen")
        cls.uom_kgm = cls.env.ref("uom.product_uom_kgm")

        cls.vendor = cls.env["res.partner"].create(
            {"name": "Uom Vendor", "supplier_rank": 1},
        )

        cls.product_unit = cls._make_product("Sold in Units", cls.uom_unit, 10.0)
        cls.product_dozen = cls._make_product("Sold in Dozens", cls.uom_dozen, 120.0)
        cls.product_kgm = cls._make_product(
            "Sold in kg",
            cls.uom_kgm,
            5.0,
            product_uom=cls.uom_kgm,
        )

        cls.approver = cls.env["res.users"].create(
            {
                "name": "Uom Approver",
                "login": "approver_po_uom",
                "group_ids": [
                    Command.set([cls.env.ref("purchase.group_purchase_manager").id]),
                ],
            },
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Uom Purchase Request",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )
        add_category_approver(cls.category, cls.approver, required=True)

    @classmethod
    def _make_product(cls, name, seller_uom, price, product_uom=None):
        return cls.env["product.product"].create(
            {
                "name": name,
                "type": "consu",
                "uom_id": (product_uom or cls.uom_unit).id,
                "seller_ids": [
                    Command.create(
                        {
                            "partner_id": cls.vendor.id,
                            "min_qty": 0.0,
                            "price": price,
                            "product_uom_id": seller_uom.id,
                        },
                    ),
                ],
            },
        )

    def _make_request(self, specs):
        return self.env["approval.request"].create(
            {
                "name": "Uom Request",
                "category_id": self.category.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": quantity,
                            "price_unit": 1.0,
                            "product_uom_id": product.uom_id.id,
                            "description": product.name,
                        },
                    )
                    for product, quantity in specs
                ],
            },
        )

    def _approve_and_create(self, request):
        request.action_confirm()
        request.with_user(self.approver).action_approve()
        request.action_create_purchase_orders()

    def _line_of(self, request, product):
        return request.line_ids.filtered(
            lambda line, product=product: line.product_id == product,
        ).purchase_order_line_id

    def test_each_line_keeps_its_own_vendor_uom(self):
        request = self._make_request(
            [(self.product_dozen, 12.0), (self.product_unit, 12.0)],
        )

        self._approve_and_create(request)

        dozen_line = self._line_of(request, self.product_dozen)
        unit_line = self._line_of(request, self.product_unit)

        self.assertEqual(dozen_line.order_id, unit_line.order_id, "one PO, one vendor")
        self.assertEqual(dozen_line.product_uom_id, self.uom_dozen)
        self.assertEqual(dozen_line.product_qty, 1.0, "12 Units is 1 Dozen")
        self.assertEqual(dozen_line.price_unit, 120.0)
        self.assertEqual(
            unit_line.product_uom_id,
            self.uom_unit,
            "the Units line must not inherit the Dozens vendor UoM",
        )
        self.assertEqual(unit_line.product_qty, 12.0)
        self.assertEqual(unit_line.price_unit, 10.0)

    def test_first_line_does_not_dictate_the_others(self):
        request = self._make_request(
            [(self.product_unit, 12.0), (self.product_dozen, 12.0)],
        )

        self._approve_and_create(request)

        self.assertEqual(
            self._line_of(request, self.product_dozen).product_uom_id,
            self.uom_dozen,
            "reversing the line order must not move the damage to the other line",
        )
        self.assertEqual(
            self._line_of(request, self.product_unit).product_uom_id,
            self.uom_unit,
        )

    def test_vendor_uoms_in_different_categories_still_produce_the_po(self):
        request = self._make_request(
            [(self.product_unit, 12.0), (self.product_kgm, 3.0)],
        )

        self._approve_and_create(request)

        self.assertEqual(
            self._line_of(request, self.product_kgm).product_uom_id,
            self.uom_kgm,
            "kg and Units share no reference unit: converting across them "
            "used to raise and left the approved request without its PO",
        )
        self.assertEqual(self._line_of(request, self.product_kgm).product_qty, 3.0)
        self.assertEqual(
            self._line_of(request, self.product_unit).product_uom_id,
            self.uom_unit,
        )


@tagged("post_install", "-at_install")
class TestPurchaseOrderCount(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.vendor = cls.env["res.partner"].create(
            {"name": "Count Vendor", "supplier_rank": 1},
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Count Product",
                "type": "consu",
                "seller_ids": [
                    Command.create(
                        {"partner_id": cls.vendor.id, "min_qty": 0.0, "price": 10.0},
                    ),
                ],
            },
        )
        cls.approver = cls.env["res.users"].create(
            {
                "name": "Count Approver",
                "login": "approver_po_count",
                "group_ids": [
                    Command.set([cls.env.ref("purchase.group_purchase_manager").id]),
                ],
            },
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Count Purchase Request",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )
        add_category_approver(cls.category, cls.approver, required=True)

    def _requests(self, count):
        requests = self.env["approval.request"]
        for index in range(count):
            requests |= self.env["approval.request"].create(
                {
                    "name": f"Count Request {index}",
                    "category_id": self.category.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "quantity": 1.0,
                                "price_unit": 10.0,
                                "product_uom_id": self.product.uom_id.id,
                                "description": self.product.name,
                            },
                        ),
                    ],
                },
            )
        self.env.flush_all()
        return requests

    def test_the_count_does_not_cost_a_query_per_request(self):
        few = self._requests(2)
        many = self._requests(8)

        with self.assertQueryCount(__system__=3):
            few.invalidate_recordset()
            self.env.invalidate_all()
            few.mapped("count_purchase_order")

        with self.assertQueryCount(__system__=3):
            many.invalidate_recordset()
            self.env.invalidate_all()
            many.mapped("count_purchase_order")

    def test_the_count_still_sees_both_sources(self):
        request = self._requests(1)

        self.assertEqual(request.count_purchase_order, 0)

        request.action_confirm()
        request.with_user(self.approver).action_approve()
        request.action_create_purchase_orders()
        request.invalidate_recordset()

        self.assertEqual(
            request.count_purchase_order,
            1,
            "orders reached through the request lines still count",
        )


@tagged("post_install", "-at_install")
class TestPurchaseOrderCreationVendorMinQty(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.vendor = cls.env["res.partner"].create(
            {"name": "MinQty Vendor", "supplier_rank": 1},
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Sold by the hundred",
                "type": "consu",
                "seller_ids": [
                    Command.create(
                        {
                            "partner_id": cls.vendor.id,
                            "min_qty": 100.0,
                            "price": 10.0,
                        },
                    ),
                ],
            },
        )
        cls.approver = cls.env["res.users"].create(
            {
                "name": "MinQty Approver",
                "login": "approver_po_min_qty",
                "group_ids": [
                    Command.set([cls.env.ref("purchase.group_purchase_manager").id]),
                ],
            },
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "MinQty Purchase Request",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )
        add_category_approver(cls.category, cls.approver, required=True)

    def _approved_request(self, quantity):
        request = self.env["approval.request"].create(
            {
                "name": "MinQty Request",
                "category_id": self.category.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": quantity,
                            "price_unit": 10.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": self.product.name,
                        },
                    ),
                ],
            },
        )
        request.action_confirm()
        request.with_user(self.approver).action_approve()
        return request

    def test_product_uom_qty_converts_to_the_product_uom(self):
        request = self._approved_request(24.0)

        self.assertEqual(
            request.line_ids.product_uom_qty,
            24.0,
            "the field converts into the product's reference UoM, which is "
            "what the vendor lookup compares against min_qty — the vendor's "
            "own purchase UoM is a different number",
        )

    def test_quantity_below_min_qty_is_reported_not_crashed(self):
        request = self._approved_request(1.0)

        with self.assertRaises(UserError) as caught:
            request.action_create_purchase_orders()

        self.assertIn(
            self.product.display_name,
            str(caught.exception),
            "the error must name the product; it used to be a NOT NULL "
            "violation on purchase_order.currency_id instead",
        )

    def test_quantity_at_min_qty_still_creates_the_order(self):
        request = self._approved_request(100.0)

        request.action_create_purchase_orders()

        order = request.line_ids.purchase_order_line_id.order_id
        self.assertEqual(order.partner_id, self.vendor)
        self.assertEqual(order.line_ids.product_qty, 100.0)


@tagged("post_install", "-at_install")
class TestPurchaseOrderCreationMultiCompany(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_b = cls.env["res.company"].create({"name": "Approval Company B"})
        cls.env.user.company_ids = [Command.link(cls.company_b.id)]

        cls.vendor = cls.env["res.partner"].create(
            {"name": "Multi Company Vendor", "supplier_rank": 1},
        )
        cls.term_b = cls.env["account.payment.term"].create(
            {"name": "Company B Term", "company_id": cls.company_b.id},
        )
        cls.vendor.with_company(
            cls.company_b
        ).property_supplier_payment_term_id = cls.term_b

        cls.product = cls.env["product.product"].create(
            {
                "name": "Multi Company Product",
                "type": "consu",
                "seller_ids": [
                    Command.create(
                        {
                            "partner_id": cls.vendor.id,
                            "min_qty": 0.0,
                            "price": 10.0,
                        },
                    ),
                ],
            },
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Multi Company Purchase Request",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
                "company_id": False,
            },
        )

    def test_document_values_use_the_request_company(self):
        request = self.env["approval.request"].create(
            {
                "name": "Multi Company Request",
                "category_id": self.category.id,
                "company_id": self.company_b.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 10.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": self.product.name,
                        },
                    ),
                ],
            },
        )
        self.assertNotEqual(
            self.env.company,
            self.company_b,
            "the point of the test is that the active company is another one",
        )

        values = request._prepare_target_document_values(
            self.vendor.id,
            request.line_ids,
        )

        self.assertEqual(
            values["payment_term_id"],
            self.term_b.id,
            "the payment term must come from the request's company, not from "
            "whichever company the approver happens to be working in",
        )
        self.assertEqual(values["company_id"], self.company_b.id)

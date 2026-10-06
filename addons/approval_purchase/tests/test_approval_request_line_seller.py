from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestApprovalRequestLineSeller(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.vendor = cls.env["res.partner"].create(
            {"name": "Seller Vendor", "supplier_rank": 1},
        )
        cls.other_vendor = cls.env["res.partner"].create(
            {"name": "Seller Other Vendor", "supplier_rank": 1},
        )
        cls.product = cls._make_product("Seller Product", cls.vendor)
        cls.foreign_product = cls._make_product("Foreign Product", cls.other_vendor)

        cls.category = cls.env["approval.category"].create(
            {
                "name": "Seller Purchase Request",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )

    @classmethod
    def _make_product(cls, name, vendor):
        return cls.env["product.product"].create(
            {
                "name": name,
                "type": "consu",
                "seller_ids": [
                    Command.create(
                        {"partner_id": vendor.id, "min_qty": 0.0, "price": 10.0},
                    ),
                ],
            },
        )

    def _make_request(self, **line_values):
        return self.env["approval.request"].create(
            {
                "name": "Seller Request",
                "category_id": self.category.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 10.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": self.product.name,
                            **line_values,
                        },
                    ),
                ],
            },
        )

    def test_foreign_seller_is_rejected_on_create(self):
        with self.assertRaises(ValidationError):
            self._make_request(seller_id=self.foreign_product.seller_ids[0].id)

    def test_foreign_seller_is_rejected_on_write(self):
        request = self._make_request()

        with self.assertRaises(ValidationError):
            request.line_ids.seller_id = self.foreign_product.seller_ids[0]

    def test_own_seller_is_accepted(self):
        request = self._make_request(seller_id=self.product.seller_ids[0].id)

        self.assertEqual(request.line_ids.seller_id.partner_id, self.vendor)
        self.assertEqual(
            request._get_target_group_key(request.line_ids),
            self.vendor.id,
        )

    def test_the_chosen_seller_prices_the_purchase_order_line(self):
        """A hand-picked pricelist line must survive into the purchase order.

        The product carries two rows for the same vendor. Core's own
        ``_select_seller`` would take the first by sequence, so if the resolved
        seller is not handed to ``_prepare_purchase_order_line`` the buyer's
        choice is silently replaced by the cheaper row.
        """
        approver = self.env["res.users"].create(
            {
                "name": "Seller Approver",
                "login": "seller_approver",
                "group_ids": [
                    Command.set([self.env.ref("purchase.group_purchase_manager").id]),
                ],
            },
        )
        add_category_approver(self.category, approver, required=True)
        preferred = self.env["product.supplierinfo"].create(
            {
                "partner_id": self.vendor.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "min_qty": 0.0,
                "price": 99.0,
                "sequence": 2,
            },
        )
        self.assertEqual(
            self.product.with_company(self.env.company)._select_seller(
                quantity=1.0,
                uom_id=self.product.uom_id,
            ),
            self.product.seller_ids[0],
            "the default lookup must prefer the first row, or the test proves nothing",
        )

        request = self._make_request(seller_id=preferred.id)
        request.action_confirm()
        request.with_user(approver).action_approve()
        request.action_create_purchase_orders()

        order_line = request.line_ids.purchase_order_line_id

        self.assertEqual(
            order_line.price_unit,
            99.0,
            "the purchase order must be priced from the chosen pricelist line",
        )

    def test_changing_the_product_drops_a_stale_seller(self):
        request = self._make_request(seller_id=self.product.seller_ids[0].id)
        line = request.line_ids

        form_line = line.new(origin=line)
        form_line.product_id = self.foreign_product
        form_line._onchange_product_id_clear_seller()

        self.assertFalse(
            form_line.seller_id,
            "the onchange must clear a vendor that does not sell the new product",
        )

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestApprovalRequirements(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env.company.write(
            {
                "po_validation_level": "manager_amount",
                "po_validation_amount": 1000.0,
            }
        )

        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Normal Vendor",
                "supplier_rank": 1,
                "po_approval_required": False,
            },
        )

        cls.flagged_vendor = cls.env["res.partner"].create(
            {
                "name": "Flagged Vendor",
                "supplier_rank": 1,
                "po_approval_required": True,
            },
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
                "list_price": 100.0,
                "standard_price": 75.0,
            },
        )

        cls.flagged_category = cls.env["product.category"].create(
            {
                "name": "Flagged Category",
                "po_approval_required": True,
            },
        )

        cls.flagged_product = cls.env["product.product"].create(
            {
                "name": "Flagged Product",
                "type": "consu",
                "categ_id": cls.flagged_category.id,
                "list_price": 50.0,
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.vendor.id,
                            "min_qty": 1.0,
                            "price": 50.0,
                        },
                    ),
                ],
            },
        )

        cls.approver = cls.env["res.users"].create(
            {
                "name": "Approver",
                "login": "approver",
                "group_ids": [
                    (6, 0, [cls.env.ref("purchase.group_purchase_manager").id]),
                ],
            },
        )

        cls.category = cls.env["approval.category"].create(
            {
                "name": "Standard PO Approval",
                "approval_type": "purchase",
                "target_model": False,
                "approval_minimum": 1,
                "order_approval_mode": "amount",
                "order_amount_min": 1000.0,
                "order_amount_max": 10000.0,
                "company_id": cls.env.company.id,
            },
        )

        add_category_approver(cls.category, cls.approver, required=True)

    def test_approval_required_by_amount(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 50.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(po.approval_required, "PO above threshold requires approval")

    def test_no_approval_below_threshold(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 5.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            po.approval_required,
            "PO below threshold doesn't require approval",
        )

    def test_approval_required_for_flagged_vendor(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.flagged_vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            po.approval_required,
            "Flagged vendor requires approval regardless of amount",
        )

    def test_approval_required_for_flagged_product_category(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.flagged_product.id,
                            "product_qty": 1.0,
                            "price_unit": 50.0,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            po.approval_required,
            "Flagged product category requires approval regardless of amount",
        )

    def test_no_approval_for_po_from_approved_request(self):
        creation_category = self.env["approval.category"].create(
            {
                "name": "Purchase Request",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )

        add_category_approver(creation_category, self.approver, required=True)

        approval = self.env["approval.request"].create(
            {
                "name": "Test Request",
                "category_id": creation_category.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.flagged_product.id,
                            "quantity": 100.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": "Test",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()

        approval.action_create_purchase_orders()
        po = approval.line_ids.purchase_order_line_id.order_id

        self.assertFalse(
            po.approval_required,
            "PO from approved request should not require re-approval",
        )

    def test_approval_requirement_recomputes_on_amount_change(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 5.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(po.approval_required, "Initially below threshold")

        po.line_ids.product_qty = 50.0

        po._compute_approval_required()

        self.assertTrue(
            po.approval_required,
            "Should require approval after amount increase",
        )

    def test_rate_limit_settings_invalidate_the_requirement(self):
        manager = self.env["res.users"].create(
            {
                "name": "Rate Limit Manager",
                "login": "rate_limit_manager",
                "group_ids": [
                    (6, 0, [self.env.ref("purchase.group_purchase_manager").id]),
                ],
            },
        )
        self.env.company.write(
            {
                "po_validation_level": "manager_amount",
                "po_validation_amount": 1000000.0,
                "po_rate_limit_enabled": False,
            },
        )
        order = (
            self.env["purchase.order"]
            .with_user(manager)
            .create(
                {
                    "partner_id": self.vendor.id,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "product_qty": 1.0,
                                "price_unit": 10.0,
                            },
                        ),
                    ],
                },
            )
        )
        order.invalidate_recordset()

        self.assertFalse(order.approval_required, "rate limiting is off")

        self.env.company.write(
            {
                "po_rate_limit_enabled": True,
                "po_rate_limit_count": 1,
                "po_rate_limit_amount": 1.0,
            },
        )

        self.assertTrue(
            order.approval_required,
            "the rate-limit settings feed the compute, so writing them must "
            "invalidate it — without them in @api.depends the record kept "
            "serving the stale value until something else flushed the cache",
        )

    def test_below_threshold_no_approval_for_manager(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 5.0,
                            "price_unit": 75.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            po.approval_required,
            "Manager below threshold doesn't need approval",
        )

    def test_validation_level_none_skips_approval(self):
        company = self.env.company
        company.po_validation_level = "none"

        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 100.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            po.approval_required,
            "Validation level 'none' bypasses amount-based approval",
        )

        company.po_validation_level = "manager_amount"

    def test_rate_limit_exceeded_requires_approval(self):
        company = self.env.company
        company.write(
            {
                "po_rate_limit_enabled": True,
                "po_rate_limit_count": 2,
                "po_rate_limit_hours": 24,
            }
        )

        for _ in range(2):
            self.env["purchase.order"].create(
                {
                    "partner_id": self.vendor.id,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "product_qty": 1.0,
                                "price_unit": 50.0,
                            },
                        ),
                    ],
                },
            )

        po_over_limit = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": 50.0,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            po_over_limit.approval_required,
            "Manager exceeding rate limit should require approval",
        )


ORDER_MODEL = "purchase.order"
LINE_FIELD = "line_ids"
LINE_EXTRA = {
    "product_qty": 1,
    "date_commitment": fields.Datetime.now(),
    "tax_ids": [(5, 0, 0)],
}
RATE_LIMIT_SETTINGS = {
    "po_rate_limit_enabled": True,
    "po_rate_limit_hours": 24,
    "po_rate_limit_count": 3,
    "po_rate_limit_amount": 2500.0,
    "po_validation_amount": 1000.0,
}
ACTOR_GROUPS = ("purchase.group_purchase_user",)
DISABLE_FIELD = "po_rate_limit_enabled"


@tagged("post_install", "-at_install")
class TestRateLimitCurrencySafety(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company_currency = cls.company.currency_id
        cls.foreign = (
            cls.env["res.currency"]
            .sudo()
            .with_context(active_test=False)
            .search([("id", "!=", cls.company_currency.id)], limit=1)
        )
        cls.foreign.active = True
        cls.env["res.currency.rate"].sudo().search(
            [("currency_id", "=", cls.foreign.id)]
        ).unlink()
        cls.env["res.currency.rate"].sudo().create(
            {
                "currency_id": cls.foreign.id,
                "company_id": cls.company.id,
                "name": fields.Date.today() - timedelta(days=1),
                "rate": 20.0,
            },
        )
        cls.company.sudo().write(RATE_LIMIT_SETTINGS)
        cls.buyer = (
            cls.env["res.users"]
            .with_context(
                no_reset_password=True,
            )
            .create(
                {
                    "name": "Rate Limit Actor",
                    "login": "rate_limit_actor",
                    "email": "rate.limit@test.com",
                    "company_id": cls.company.id,
                    "company_ids": [(6, 0, [cls.company.id])],
                    "group_ids": [(4, cls.env.ref(group).id) for group in ACTOR_GROUPS],
                },
            )
        )
        cls.partner = cls.env["res.partner"].create({"name": "Rate Limit Partner"})
        cls.product = cls.env["product.product"].create(
            {"name": "Rate Limit Widget", "purchase_ok": True, "sale_ok": True},
        )

    def _order(self, currency, company_currency_value):
        rate = 20.0 if currency != self.company_currency else 1.0
        return (
            self.env[ORDER_MODEL]
            .with_user(self.buyer)
            .create(
                {
                    "partner_id": self.partner.id,
                    "currency_id": currency.id,
                    "company_id": self.company.id,
                    LINE_FIELD: [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "name": "l",
                                "price_unit": company_currency_value * rate,
                                **LINE_EXTRA,
                            },
                        ),
                    ],
                },
            )
        )

    def _three_foreign_peers_under_threshold(self):
        for _ in range(3):
            self._order(self.foreign, 900.0)
        self.env.flush_all()

    def test_limit_does_not_depend_on_the_order_currency(self):
        self._three_foreign_peers_under_threshold()

        in_foreign = self._order(self.foreign, 900.0)._check_rate_limit_exceeded()
        in_company = self._order(
            self.company_currency, 900.0
        )._check_rate_limit_exceeded()

        self.assertEqual(
            in_foreign,
            in_company,
            "Three prior orders either trip the rate limit or they do not. "
            "The currency of the order being checked must not decide it.",
        )

    def test_the_count_limit_trips_on_foreign_peers(self):
        self._three_foreign_peers_under_threshold()

        self.assertTrue(
            self._order(self.company_currency, 900.0)._check_rate_limit_exceeded(),
            "Three sub-threshold orders reach the count limit of 3 whatever "
            "currency they were booked in.",
        )

    def test_orders_over_the_threshold_never_count(self):
        for _ in range(3):
            self._order(self.foreign, 5000.0)
        self.env.flush_all()

        self.assertFalse(
            self._order(self.company_currency, 10.0)._check_rate_limit_exceeded(),
            "Orders above the approval threshold go through approval on their "
            "own merits and must not feed the split-order limit.",
        )

    def test_cumulative_amount_is_summed_in_company_currency(self):
        for _ in range(2):
            self._order(self.foreign, 900.0)
        self.env.flush_all()

        self.assertTrue(
            self._order(self.company_currency, 900.0)._check_rate_limit_exceeded(),
            "2 x 900 in foreign currency plus 900 is 2700 in company currency, "
            "past the 2500 cumulative limit — summing the raw foreign "
            "amount_total instead would have tripped it far earlier, and "
            "summing them as if they were company currency far later.",
        )

    def test_disabled_rate_limiting_short_circuits(self):
        self.company.sudo().write({DISABLE_FIELD: False})
        self._three_foreign_peers_under_threshold()

        self.assertFalse(
            self._order(self.company_currency, 900.0)._check_rate_limit_exceeded(),
        )

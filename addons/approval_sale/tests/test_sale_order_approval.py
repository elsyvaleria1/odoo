from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import pool_step


def _create_sales_user(env, login):
    return env["res.users"].create(
        {
            "name": login,
            "login": login,
            "group_ids": [
                (4, env.ref("base.group_user").id),
                (4, env.ref("sale.group_sale_salesman").id),
            ],
        }
    )


def _create_partner(env, **vals):
    if "credit_exception" in env["res.partner"]._fields:
        vals.setdefault("credit_exception", True)
    return env["res.partner"].create(vals)


@tagged("post_install", "-at_install")
class TestSaleOrderApprovalRequired(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.company.write(
            {
                "so_validation_level": "manager_amount",
                "so_validation_amount": 1000.0,
            },
        )
        cls.user = _create_sales_user(cls.env, "approval_sale_required")

        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Test Customer",
                "company_id": cls.company.id,
            },
        )

        cls.customer_approval = cls.env["res.partner"].create(
            {
                "name": "High Risk Customer",
                "company_id": cls.company.id,
                "so_approval_required": True,
            },
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Standard Product",
                "type": "consu",
                "list_price": 100.0,
            },
        )

        cls.product_approval = cls.env["product.product"].create(
            {
                "name": "Controlled Product",
                "type": "consu",
                "list_price": 500.0,
                "so_approval_required": True,
            },
        )

        cls.categ_approval = cls.env["product.category"].create(
            {
                "name": "Controlled Category",
                "so_approval_required": True,
            },
        )

        cls.product_categ_approval = cls.env["product.product"].create(
            {
                "name": "Category Controlled Product",
                "type": "consu",
                "list_price": 100.0,
                "categ_id": cls.categ_approval.id,
            },
        )

    def _create_sale_order(self, partner, product, qty=1):
        return (
            self.env["sale.order"]
            .with_user(self.user)
            .create(
                {
                    "partner_id": partner.id,
                    "company_id": self.company.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_qty": qty,
                                "price_unit": product.list_price,
                            },
                        ),
                    ],
                },
            )
        )

    def test_approval_required_customer_flagged(self):
        order = self._create_sale_order(self.customer_approval, self.product, 1)

        self.assertTrue(order.approval_required)

    def test_approval_required_product_flagged(self):
        order = self._create_sale_order(self.customer, self.product_approval, 1)

        self.assertTrue(order.approval_required)

    def test_approval_required_product_category_flagged(self):
        order = self._create_sale_order(self.customer, self.product_categ_approval, 1)

        self.assertTrue(order.approval_required)

    def test_approval_required_amount_threshold(self):
        order = self._create_sale_order(self.customer, self.product, 50)

        self.assertTrue(
            order.approval_required,
            f"Expected approval_required=True for amount_total={order.amount_total} "
            f"with threshold={self.company.so_validation_amount} "
            f"(company currency={self.company.currency_id.name}, "
            f"order currency={order.currency_id.name})",
        )

    def test_approval_not_required_validation_none(self):
        self.company.so_validation_level = "none"

        order = self._create_sale_order(self.customer, self.product, 50)

        self.assertFalse(order.approval_required)

    def test_approval_not_required_below_threshold_manager(self):
        self.user.group_ids = [
            (4, self.env.ref("sale.group_sale_manager").id),
        ]

        order = self._create_sale_order(self.customer, self.product, 5)

        self.assertFalse(order.approval_required)


@tagged("post_install", "-at_install")
class TestSaleOrderApprovalWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.company.write(
            {
                "so_validation_level": "manager_amount",
                "so_validation_amount": 500.0,
            },
        )

        cls.customer = _create_partner(
            cls.env,
            name="Test Customer",
            company_id=cls.company.id,
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
                "list_price": 100.0,
            },
        )

        existing_sale_categories = cls.env["approval.category"].search(
            [("approval_type", "=", "sale"), ("active", "=", True)],
        )
        existing_sale_categories.write({"active": False})

        cls.approval_category = cls.env["approval.category"].create(
            {
                "name": "Sales Approval Test",
                "company_id": cls.company.id,
                "approval_type": "sale",
                "approval_minimum": 1,
                "allow_self_approval": True,
                "step_ids": pool_step([(cls.env.user.id, True, 10)], minimum=1),
            },
        )

    def _create_sale_order(self, qty=1):
        return self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": qty,
                            "price_unit": self.product.list_price,
                        },
                    ),
                ],
            },
        )

    def _create_approved_approval(self, order):
        approval = self.env["approval.request"].create(
            {
                "name": "Test Approval",
                "category_id": self.approval_category.id,
                "company_id": self.company.id,
                "request_owner_id": self.env.user.id,
                "res_model": order._name,
                "res_id": order.id,
                "amount": order.amount_total,
                "currency_id": order.currency_id.id,
            },
        )
        approval.action_confirm()
        approval.action_approve()
        return approval

    def _create_pending_approval(self, order):
        approval = self.env["approval.request"].create(
            {
                "name": "Test Approval",
                "category_id": self.approval_category.id,
                "company_id": self.company.id,
                "request_owner_id": self.env.user.id,
                "res_model": order._name,
                "res_id": order.id,
            },
        )
        self.assertIn(
            self.env.user,
            approval.approver_ids.user_id,
            "the category's approver must have been seeded onto the request",
        )
        approval.action_confirm()
        return approval

    def test_action_confirm_requires_approval(self):
        order = self._create_sale_order(10)

        self.assertTrue(order.approval_required)

        result = order.action_confirm()

        self.assertIn(
            result.get("type"),
            ("ir.actions.act_window", "ir.actions.client"),
            f"Expected approval request action, got: {result}",
        )
        self.assertTrue(order.approval_request_id)

    def test_module_data_confirms_an_order_that_needs_approval(self):
        order = self._create_sale_order(10)
        self.assertTrue(order.approval_required)

        order.with_context(install_module="sale_project").action_confirm()

        self.assertEqual(order.state, "done")
        self.assertFalse(order.approval_request_id)

    def test_module_data_moves_an_order_past_the_confirm_checkpoint(self):
        order = self._create_sale_order(10)
        self.assertTrue(order.approval_required)

        order.with_context(install_module="event_sale").write({"state": "done"})

        self.assertEqual(order.state, "done")
        with self.assertRaises(UserError):
            self._create_sale_order(10).write({"state": "done"})

    def test_action_confirm_pending_approval(self):
        order = self._create_sale_order(10)

        approval = self._create_pending_approval(order)
        order.approval_request_id = approval

        with self.assertRaises(UserError) as context:
            order.action_confirm()

        self.assertIn("pending approval", str(context.exception))

    def test_a_pending_request_holds_an_order_that_needs_no_approval(self):
        order = self._create_sale_order(1)
        self.assertFalse(order.approval_required, "below the threshold")
        order.approval_request_id = self._create_pending_approval(order)

        with self.assertRaises(UserError):
            order.action_confirm()
        with self.assertRaises(UserError):
            order.write({"state": "done"})
        self.assertEqual(order.state, "draft")

    def test_action_confirm_approved_confirms_order(self):
        order = self._create_sale_order(10)

        self.assertTrue(order.approval_required)

        approval = self._create_approved_approval(order)
        order.approval_request_id = approval

        self.assertEqual(order.approval_state, "approved")

        result = order.action_confirm()

        self.assertEqual(
            order.state,
            "done",
            f"Order was not confirmed. State is '{order.state}' instead of 'done'",
        )
        self.assertTrue(
            result is True
            or result == {}
            or result.get("type") != "ir.actions.act_window",
            "Order was sent for re-approval instead of being confirmed",
        )

    def test_action_cancel_cancels_approval(self):
        order = self._create_sale_order(10)

        approval = self._create_pending_approval(order)
        order.approval_request_id = approval

        order.action_cancel()

        self.assertEqual(approval.state, "refused")

    def test_reset_to_draft_after_refusal_drops_the_refused_link(self):
        order = self._create_sale_order(10)
        approval = self._create_pending_approval(order)
        order.approval_request_id = approval
        order.action_cancel()
        self.assertEqual(order.approval_state, "refused")

        order.action_draft()

        self.assertEqual(order.state, "draft")
        self.assertFalse(order.approval_request_id)
        self.assertFalse(order.approval_state)

    def test_get_approval_required_fields(self):
        order = self._create_sale_order(1)

        required_fields = order._get_fields_approval_required()

        self.assertIn("partner_id", required_fields)
        self.assertIn("line_ids", required_fields)


@tagged("post_install", "-at_install")
class TestSaleOrderApprovalRateLimit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.company.write(
            {
                "so_validation_level": "manager_amount",
                "so_validation_amount": 1000.0,
                "so_rate_limit_enabled": True,
                "so_rate_limit_hours": 24,
                "so_rate_limit_count": 3,
                "so_rate_limit_amount": 2000.0,
            },
        )
        cls.user = _create_sales_user(cls.env, "approval_sale_rate_limit")
        cls.user.group_ids = [
            (4, cls.env.ref("sale.group_sale_manager").id),
        ]

        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Test Customer",
                "company_id": cls.company.id,
            },
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
                "list_price": 100.0,
            },
        )

    def _create_sale_order(self, amount):
        return (
            self.env["sale.order"]
            .with_user(self.user)
            .create(
                {
                    "partner_id": self.customer.id,
                    "company_id": self.company.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_qty": 1,
                                "price_unit": amount,
                                "tax_ids": [Command.clear()],
                            },
                        ),
                    ],
                },
            )
        )

    def test_rate_limit_not_exceeded(self):
        order = self._create_sale_order(500)

        self.assertFalse(order._check_rate_limit_exceeded())

    def test_rate_limit_exceeded_by_count(self):
        for _i in range(3):
            self._create_sale_order(100)

        order = self._create_sale_order(100)

        self.assertTrue(order._check_rate_limit_exceeded())

    def test_rate_limit_exceeded_by_amount(self):
        self._create_sale_order(900)
        self._create_sale_order(900)

        order = self._create_sale_order(500)

        self.assertTrue(order._check_rate_limit_exceeded())

    def test_rate_limit_disabled(self):
        self.company.so_rate_limit_enabled = False

        for _i in range(5):
            self._create_sale_order(500)

        order = self._create_sale_order(500)

        self.assertFalse(order._check_rate_limit_exceeded())

    def test_toggling_the_rate_limiter_recomputes_approval_required(self):
        self.company.so_rate_limit_enabled = False
        order = self._create_sale_order(500)

        self.assertFalse(order.approval_required)

        self.company.write(
            {
                "so_rate_limit_enabled": True,
                "so_rate_limit_count": 1000,
                "so_rate_limit_amount": 0.01,
            },
        )

        self.assertTrue(
            order.approval_required,
            "enabling the rate limiter must invalidate approval_required in "
            "the same transaction; a stale False means the compute's depends "
            "misses the company rate-limit fields it reads",
        )

    def test_rate_limit_is_pinned_to_creator_not_viewer(self):
        for _i in range(3):
            self._create_sale_order(100)
        order = self._create_sale_order(100)
        self.assertTrue(order._check_rate_limit_exceeded())
        order.invalidate_recordset(["approval_required"])
        self.assertTrue(order.approval_required)

        other_manager = self.env["res.users"].create(
            {
                "name": "Other Sales Manager",
                "login": "other_sales_manager_rate",
                "email": "other.manager.rate@test.com",
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
                "group_ids": [
                    (4, self.env.ref("sale.group_sale_manager").id),
                    (4, self.env.ref("base.group_user").id),
                ],
            },
        )
        order_as_other = order.with_user(other_manager)
        self.assertTrue(order_as_other._check_rate_limit_exceeded())
        order_as_other.invalidate_recordset(["approval_required"])
        self.assertTrue(
            order_as_other.approval_required,
            "the rate-limit verdict must follow the creator, not the viewer",
        )


@tagged("post_install", "-at_install")
class TestSaleOrderApprovalLocking(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Test Customer",
                "company_id": cls.company.id,
            },
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
                "list_price": 100.0,
            },
        )

        cls.approval_category = cls.env["approval.category"].create(
            {
                "name": "Sales Approval",
                "allow_self_approval": True,
                "company_id": cls.company.id,
                "approval_type": "sale",
            },
        )

    def test_should_be_locked_no_approval(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
            },
        )

        self.assertFalse(order._is_lock_required())

    def test_should_be_locked_approved(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
            },
        )

        approval = self.env["approval.request"].create(
            {
                "name": "Test Approval",
                "category_id": self.approval_category.id,
                "company_id": self.company.id,
                "request_owner_id": self.env.user.id,
                "res_model": order._name,
                "res_id": order.id,
            },
        )
        self.env["approval.approver"].create(
            {
                "request_id": approval.id,
                "user_id": self.env.user.id,
                "required": True,
            },
        )._record_decision("approved")
        order.approval_request_id = approval

        self.assertEqual(order.approval_state, "approved")
        self.assertTrue(order._is_lock_required())

    def test_should_be_locked_pending(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
            },
        )

        approval = self.env["approval.request"].create(
            {
                "name": "Test Approval",
                "category_id": self.approval_category.id,
                "company_id": self.company.id,
                "request_owner_id": self.env.user.id,
                "res_model": order._name,
                "res_id": order.id,
            },
        )
        self.env["approval.approver"].create(
            {
                "request_id": approval.id,
                "user_id": self.env.user.id,
                "flow_state": "new",
                "required": True,
            },
        )
        approval.action_confirm()
        order.approval_request_id = approval

        self.assertFalse(order._is_lock_required())


@tagged("post_install", "-at_install")
class TestSaleApprovalWithdrawGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.partner = _create_partner(cls.env, name="Withdraw Guard Partner")
        cls.product = cls.env["product.product"].create(
            {"name": "Withdraw Guard Product", "type": "consu", "list_price": 50.0},
        )
        cls.env["approval.category"].search(
            [("approval_type", "=", "sale"), ("active", "=", True)],
        ).write({"active": False})
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Sale Withdraw Guard",
                "company_id": cls.company.id,
                "approval_type": "sale",
                "approval_minimum": 1,
                "allow_self_approval": True,
                "target_model": "sale.order",
                "has_product": "required",
                "step_ids": pool_step([(cls.env.user.id, True, 10)], minimum=1),
            }
        )

    def _approved_request(self):
        request = self.env["approval.request"].create(
            {
                "name": "Sale Withdraw Test",
                "category_id": self.category.id,
                "company_id": self.company.id,
                "request_owner_id": self.env.user.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, "quantity": 1.0})
                ],
            }
        )
        request.action_confirm()
        request.approver_ids[0].with_context(skip_wizard=True).action_approve()
        self.assertEqual(request.state, "approved")
        return request

    def test_withdraw_allowed_without_descendant(self):
        request = self._approved_request()
        request._check_withdraw_allowed()

    def test_withdraw_blocked_with_active_sale_order(self):
        request = self._approved_request()
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1,
                            "price_unit": 50.0,
                        },
                    ),
                ],
            }
        )
        request._link_produced_documents(order)
        with self.assertRaises(UserError):
            request._check_withdraw_allowed()

    def test_withdraw_unblocks_when_so_cancelled(self):
        request = self._approved_request()
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1,
                            "price_unit": 50.0,
                        },
                    ),
                ],
            }
        )
        request._link_produced_documents(order)
        order._action_cancel()
        self.assertEqual(order.state, "cancel")
        request._check_withdraw_allowed()


ORDER_MODEL = "sale.order"
LINE_FIELD = "line_ids"
LINE_EXTRA = {
    "product_qty": 1,
    "tax_ids": [(5, 0, 0)],
}
RATE_LIMIT_SETTINGS = {
    "so_rate_limit_enabled": True,
    "so_rate_limit_hours": 24,
    "so_rate_limit_count": 3,
    "so_rate_limit_amount": 2500.0,
    "so_validation_amount": 1000.0,
}
ACTOR_GROUPS = ("sale.group_sale_salesman",)
DISABLE_FIELD = "so_rate_limit_enabled"


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


@tagged("post_install", "-at_install")
class TestSaleTargetRequestLines(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Sale Target Category",
                "approval_type": "sale",
                "target_model": "sale.order",
                "approval_minimum": 1,
                "allow_self_approval": True,
                "has_product": "required",
                "company_id": cls.company.id,
                "step_ids": pool_step([(cls.env.user.id, True, 10)], minimum=1),
            },
        )

    def _empty_request(self):
        return self.env["approval.request"].create(
            {
                "name": "Empty Sale Request",
                "category_id": self.category.id,
                "company_id": self.company.id,
            },
        )

    def test_the_requester_is_stopped_not_the_approver(self):
        request = self._empty_request()
        self.assertFalse(request.line_ids)

        with self.assertRaises(UserError) as caught:
            request.action_confirm()

        self.assertIn("add product lines", str(caught.exception))
        self.assertEqual(
            request.state,
            "new",
            "the empty request must not reach the approver's desk at all",
        )

    def test_a_request_with_lines_still_submits(self):
        product = self.env["product.product"].create(
            {"name": "Target Product", "type": "consu"},
        )
        request = self._empty_request()
        request.line_ids = [
            Command.create({"product_id": product.id, "quantity": 1.0}),
        ]

        request.action_confirm()

        self.assertEqual(request.state, "pending")

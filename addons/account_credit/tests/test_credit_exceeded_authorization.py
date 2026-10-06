from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, RedirectWarning, UserError, ValidationError
from odoo.service.model import call_kw
from odoo.tests.common import TransactionCase, tagged

from .common import AUTHORIZATION as MODEL
from .common import CreditAuthorizationCase


@tagged("post_install", "-at_install")
class TestCreditExceededAuthorization(CreditAuthorizationCase, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._old_categ_states = {}
        if "approval.category" in cls.env:
            sale_categories = cls.env["approval.category"].search(
                [
                    ("approval_type", "=", "sale"),
                ]
            )
            cls._old_categ_states = {c.id: c.active for c in sale_categories}
            sale_categories.write({"active": False})

        cls._old_validation_level = None
        if "so_validation_level" in cls.env["res.company"]._fields:
            cls._old_validation_level = cls.env.company.so_validation_level
            cls.env.company.write({"so_validation_level": "none"})

        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Auth Test Partner",
            }
        )
        cls.unconditional_type = cls.env["credit.grade"].create(
            {"name": "Auth Test Unconditional"}
        )
        cls.partner.write(
            {
                "credit_grade_id": cls.unconditional_type.id,
                "credit_trusted_amount": 10000.0,
            }
        )

        cls.immediate_term = cls.env["account.payment.term"].create(
            {
                "name": "Auth Immediate",
                "line_ids": [
                    Command.create(
                        {
                            "value": "percent",
                            "value_amount": 100.0,
                            "nb_days": 0,
                        }
                    )
                ],
            }
        )
        cls.credit_term = cls.env["account.payment.term"].create(
            {
                "name": "Auth 30 Days",
                "line_ids": [
                    Command.create(
                        {
                            "value": "percent",
                            "value_amount": 100.0,
                            "nb_days": 30,
                        }
                    )
                ],
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Auth Product",
                "list_price": 15000.0,
            }
        )
        cls.user = cls.env["res.users"].create(
            {
                "name": "Auth Test User",
                "login": "test_auth_credit",
                "email": "test_auth_credit@example.com",
                "company_id": cls.env.company.id,
                "company_ids": [Command.link(cls.env.company.id)],
                "group_ids": [
                    Command.link(cls.env.ref("sale.group_sale_salesman").id),
                    Command.link(cls.env.ref("account_credit.group_credit_manager").id),
                ],
            }
        )
        cls.user_readonly = cls.env["res.users"].create(
            {
                "name": "Auth Readonly User",
                "login": "test_auth_credit_readonly",
                "email": "test_auth_credit_readonly@example.com",
                "company_id": cls.env.company.id,
                "company_ids": [Command.link(cls.env.company.id)],
                "group_ids": [
                    Command.link(cls.env.ref("sale.group_sale_salesman").id),
                    Command.link(
                        cls.env.ref("account_credit.group_credit_readonly").id
                    ),
                ],
            }
        )
        cls.user_credit_user = cls.env["res.users"].create(
            {
                "name": "Auth Credit User",
                "login": "test_auth_credit_user",
                "email": "test_auth_credit_user@example.com",
                "company_id": cls.env.company.id,
                "company_ids": [Command.link(cls.env.company.id)],
                "group_ids": [
                    Command.link(cls.env.ref("sale.group_sale_salesman").id),
                    Command.link(cls.env.ref("account_credit.group_credit_user").id),
                ],
            }
        )
        cls.user_no_credit = cls.env["res.users"].create(
            {
                "name": "Auth No Credit User",
                "login": "test_auth_no_credit",
                "email": "test_auth_no_credit@example.com",
                "company_id": cls.env.company.id,
                "company_ids": [Command.link(cls.env.company.id)],
                "group_ids": [
                    Command.link(cls.env.ref("sale.group_sale_salesman").id),
                ],
            }
        )

    @classmethod
    def tearDownClass(cls):
        if cls._old_validation_level is not None:
            cls.env.company.write({"so_validation_level": cls._old_validation_level})
        for cat_id, active in cls._old_categ_states.items():
            cls.env["approval.category"].browse(cat_id).write({"active": active})
        super().tearDownClass()

    def _create_order(self, partner=None, payment_term=None, price=None):
        return (
            self.env["sale.order"]
            .with_user(self.user)
            .create(
                {
                    "partner_id": (partner or self.partner).id,
                    "payment_term_id": (payment_term or self.credit_term).id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_qty": 1.0,
                                "price_unit": price or self.product.list_price,
                            }
                        )
                    ],
                }
            )
        )

    def test_authorization_opens_on_limit_exceeded(self):
        order = self._create_order(price=15000.0)
        self._credit_authorization_action(order)
        self.assertEqual(order.state, "draft")

    def test_authorization_skipped_when_within_limit(self):
        order = self._create_order(price=5000.0)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_authorization_skipped_outside_account_credit(self):
        partner = self.env["res.partner"].create({"name": "No Limit"})
        order = self._create_order(partner=partner, price=99999.0)
        self.assertFalse(partner.use_partner_credit_limit)
        self.assertFalse(order._is_credit_limit_exceeded())

    def test_zero_limit_is_no_credit_not_unlimited(self):
        credit_type = self.env["credit.grade"].create({"name": "Zero Limit Condition"})
        partner = self.env["res.partner"].create(
            {"name": "Zero Limit", "credit_grade_id": credit_type.id}
        )
        self.assertEqual(partner.credit_status, "authorized")
        self.assertTrue(partner.use_partner_credit_limit)
        self.assertEqual(partner.credit_limit, 0.0)
        order = self._create_order(partner=partner, price=1.0)
        self.assertTrue(
            order._is_credit_limit_exceeded(),
            "a partner backed by no guarantees must not get unlimited credit",
        )

    def test_authorization_skipped_immediate(self):
        order = self._create_order(payment_term=self.immediate_term, price=15000.0)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_filtered_out_legal(self):
        partner = self.env["res.partner"].create(
            {"name": "Filtered Legal", "credit_legal_hold": True}
        )
        self.assertEqual(partner.credit_status, "legal")
        order = self._create_order(partner=partner, price=15000.0)
        self.assertFalse(order._filtered_credit_limit_orders())

    def test_filtered_out_review(self):
        review_type = self.env["credit.grade"].create(
            {
                "name": "Filtered Review Condition",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "needs a document",
                            "document_type_id": self.env["document.type"]
                            .create(
                                {"name": "Filtered Review Type", "code": "FILT_REV"}
                            )
                            .id,
                            "min_quantity": 1,
                        }
                    )
                ],
            }
        )
        partner = self.env["res.partner"].create(
            {"name": "Filtered Review", "credit_grade_id": review_type.id}
        )
        self.assertEqual(partner.credit_status, "review")
        order = self._create_order(partner=partner, price=15000.0)
        self.assertFalse(order._filtered_credit_limit_orders())

    def test_authorize_confirm(self):
        order = self._create_order(price=15000.0)
        authorization = self._credit_authorization_wizard(order)
        old_limit = self.partner.credit_limit
        authorization.action_authorize_confirm()
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertGreater(self.partner.credit_limit, old_limit)
        self.assertEqual(order.state, "done")

    def test_authorize_only(self):
        order = self._create_order(price=15000.0)
        authorization = self._credit_authorization_wizard(order)
        old_limit = self.partner.credit_limit
        old_trusted = self.partner.credit_trusted_amount
        record = authorization.action_authorize()
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertGreater(self.partner.credit_limit, old_limit)
        self.assertEqual(
            self.partner.credit_trusted_amount,
            old_trusted,
            "authorizing must not silently rewrite the standing trusted amount",
        )
        self.assertEqual(record.partner_id, self.partner)
        self.assertEqual(record.user_id, self.user)
        self.assertEqual(record.order_ids, order)
        self.assertNotEqual(order.state, "done")

    def test_authorization_is_reversible(self):
        order = self._create_order(price=15000.0)
        wizard = self._credit_authorization_wizard(order)
        baseline = self.partner.credit_limit
        record = wizard.action_authorize()
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertGreater(self.partner.credit_limit, baseline)
        record.active = False
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertEqual(
            self.partner.credit_limit,
            baseline,
            "archiving an authorization must withdraw exactly its amount",
        )
        self.assertTrue(record.exists(), "the decision must stay auditable")

    def test_skip_context_prevents_recheck(self):
        order = self._create_order(price=15000.0)
        order.with_context(skip_credit_exceeded_authorization=True).action_confirm()
        self.assertEqual(order.state, "done")

    def test_a_client_cannot_send_the_credit_override(self):
        for key in ("credit_override", "skip_credit_exceeded_authorization"):
            with self.subTest(key=key):
                order = self._create_order(price=15000.0)
                with self.assertRaises(RedirectWarning):
                    call_kw(
                        order.browse(),
                        "action_confirm",
                        [order.ids],
                        {"context": {key: True}},
                    )
                self.assertEqual(order.state, "draft")

    def test_multi_order_different_partners(self):
        partner2 = self.env["res.partner"].create({"name": "Auth Partner 2"})
        partner2.write(
            {
                "credit_status": "authorized",
                "use_partner_credit_limit": True,
                "credit_limit": 10000.0,
            }
        )
        order1 = self._create_order(price=15000.0)
        order2 = self._create_order(partner=partner2, price=15000.0)
        with self.assertRaises(UserError):
            (order1 | order2).action_confirm()

    def test_amount_authorized_negative_raises(self):
        order = self._create_order(price=15000.0)
        authorization = self._credit_authorization_wizard(order)
        with self.assertRaises(ValidationError):
            authorization.write({"amount_authorized": -100.0})

    def test_uses_commercial_partner(self):
        contact = self.env["res.partner"].create(
            {
                "name": "Auth Contact",
                "parent_id": self.partner.id,
                "type": "contact",
            }
        )
        order = self._create_order(partner=contact, price=15000.0)
        authorization = self._credit_authorization_wizard(order)
        self.assertEqual(authorization.partner_id, self.partner)

    def test_no_payment_term_is_immediate_and_skips_the_limit(self):
        order = self._create_order(price=15000.0)
        order.write({"payment_term_id": False})
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_multi_order_partial_excess_holds_the_whole_batch(self):
        o_safe_1 = self._create_order(price=3000.0)
        o_safe_2 = self._create_order(price=4000.0)
        o_excess = self._create_order(price=15000.0)

        batch = o_safe_1 | o_safe_2 | o_excess
        authorization = self._credit_authorization_wizard(batch)

        for order in batch:
            self.assertEqual(
                order.state,
                "draft",
                "nothing may be confirmed while the manager still has the "
                "authorization modal open",
            )

        authorization.action_authorize_confirm()
        for order in batch:
            self.assertEqual(order.state, "done")

    def test_acl_readonly_cannot_create(self):
        with self.assertRaises(AccessError):
            self.env[MODEL].with_user(self.user_readonly).create(
                {
                    "partner_id": self.partner.id,
                    "order_ids": [Command.set([])],
                }
            )

    def test_acl_user_can_create_cannot_authorize(self):
        wiz = (
            self.env[MODEL]
            .with_user(self.user_credit_user)
            .create(
                {
                    "partner_id": self.partner.id,
                    "order_ids": [Command.set([])],
                }
            )
        )
        with self.assertRaises(AccessError):
            wiz.action_authorize()

    def test_acl_no_credit_group_cannot_create(self):
        with self.assertRaises(AccessError):
            self.env[MODEL].with_user(self.user_no_credit).create(
                {
                    "partner_id": self.partner.id,
                    "order_ids": [Command.set([])],
                }
            )

    def test_action_confirm_no_credit_group_usererror(self):
        order = (
            self.env["sale.order"]
            .with_user(self.user_no_credit)
            .create(
                {
                    "partner_id": self.partner.id,
                    "payment_term_id": self.credit_term.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_qty": 1.0,
                                "price_unit": 15000.0,
                            }
                        )
                    ],
                }
            )
        )
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_the_excess_is_authorized_by_whoever_holds_the_verb(self):
        order = self._create_order(price=15000.0)
        self.assertTrue(order._is_credit_excess_authorized_by(self.user))
        self.assertFalse(order._is_credit_excess_authorized_by(self.user_credit_user))
        self.assertFalse(order._is_credit_excess_authorized_by(self.user_no_credit))
        self.assertTrue(
            order._is_credit_excess_authorized_by(self.user_no_credit | self.user)
        )

    def test_an_approval_over_the_limit_asks_its_deciders_not_the_caller(self):
        self.env.company.so_auto_confirm_on_approval = True
        order = self._create_order(price=15000.0).with_env(self.env)
        self.assertTrue(order._is_credit_limit_exceeded())
        Order = type(order)
        notes = order.message_ids
        with patch.object(
            Order, "_get_approval_deciders", lambda order: self.user_credit_user
        ):
            order._on_approval_approved()
        posted = order.message_ids - notes
        self.assertEqual(order.state, "draft")
        self.assertEqual(
            len(posted),
            1,
            "the superuser runs the hook, but the approver was no credit manager",
        )
        self.assertIn("a credit manager must authorize the excess", posted.body)
        notes = order.message_ids
        with patch.object(Order, "_get_approval_deciders", lambda order: self.user):
            order._on_approval_approved()
        self.assertEqual(order.state, "draft")
        self.assertFalse(order.message_ids - notes)

from ast import literal_eval

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AccountApprovalCommon
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestAuditRegressions(AccountApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.product = cls.env["product.product"].create(
            {"name": "Audit Product", "type": "consu", "list_price": 100.0},
        )
        cls.category_amount = cls._new_category(
            name="Amount based",
            move_amount_min=1000.0,
        )
        cls.company_2 = cls.setup_other_company(name="regression_company_2")["company"]

    @classmethod
    def _new_category(cls, **values):
        vals = {
            "name": "Category",
            "approval_type": "accounting",
            "target_model": False,
            "approval_minimum": 1,
        }
        vals.update(values)
        category = cls.env["approval.category"].create(vals)
        add_category_approver(category, cls.approver, required=True)
        return category

    def _new_move(self, move_type="out_invoice", price=1000.0, quantity=1.0):
        account = (
            self.account_revenue
            if move_type in ("out_invoice", "out_refund")
            else self.account_expense
        )
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-06-01",
                "date": "2026-06-01",
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": quantity,
                            "price_unit": price,
                            "account_id": account.id,
                            "tax_ids": [],
                        },
                    ),
                ],
            },
        )

    def _approved_move(self, **kwargs):
        move = self._new_move(**kwargs)
        move.action_create_approval_request()
        move.approval_request_id.with_user(self.approver).action_approve()
        return move

    def test_posting_an_edited_approved_move_asks_again(self):
        move = self._approved_move(price=1000.0)
        self.assertEqual(move.approval_state, "approved")
        self.assertEqual(move.approval_request_id.amount, 1000.0)

        move.invoice_line_ids[0].price_unit = 9999.0

        move.action_post()
        self.assertEqual(move.state, "draft")
        self.assertEqual(move.approval_state, "pending", "asked again")

    def test_posting_an_unchanged_approved_move_still_works(self):
        move = self._approved_move(price=1000.0)

        move.action_post()

        self.assertEqual(move.state, "posted")

    def test_a_line_swapped_at_the_same_amount_is_not_what_was_approved(self):
        move = self._approved_move(price=1000.0)
        other = self.env["product.product"].create(
            {"name": "Swapped Product", "type": "consu", "list_price": 1.0}
        )

        move.invoice_line_ids[0].write(
            {"product_id": other.id, "price_unit": 1000.0, "tax_ids": []}
        )
        self.assertEqual(move.amount_total, move.approval_request_id.amount)

        move.action_post()
        self.assertEqual(move.state, "draft")
        self.assertEqual(move.approval_state, "pending", "asked again")

    def test_another_partner_is_not_what_was_approved(self):
        move = self._approved_move(price=1000.0)

        move.partner_id = self.partner_b

        self.assertEqual(move.approval_state, "new")
        move.action_post()
        self.assertEqual(move.state, "draft")
        self.assertEqual(move.approval_state, "pending", "asked again")

    def test_an_amount_change_keeps_the_approval_for_the_post_recheck(self):
        move = self._approved_move(price=1000.0)

        move.invoice_line_ids[0].price_unit = 1200.0

        self.assertEqual(move.approval_state, "approved")

    def test_lines_are_frozen_while_approval_is_pending(self):
        move = self._new_move(price=1000.0)
        move.action_create_approval_request()
        self.assertEqual(move.approval_state, "pending")

        with self.assertRaises(UserError):
            move.write(
                {
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "quantity": 10.0,
                                "price_unit": 1000.0,
                                "account_id": self.account_revenue.id,
                                "tax_ids": [],
                            },
                        ),
                    ],
                },
            )

    def test_partner_is_frozen_while_approval_is_pending(self):
        move = self._new_move(price=1000.0)
        move.action_create_approval_request()

        with self.assertRaises(UserError):
            move.partner_id = self.partner_b

    def test_journal_type_follows_the_source_move(self):
        category = self._new_category(
            name="With journal",
            move_amount_min=100.0,
            has_journal="required",
            account_move_type="in_invoice",
        )
        self.category_amount.active = False
        self.addCleanup(self.category_amount.write, {"active": True})

        move = self._new_move(move_type="out_invoice", price=800.0)
        move.action_create_approval_request()
        request = move.approval_request_id

        self.assertEqual(request.category_id, category)
        self.assertEqual(
            request.journal_type,
            "sale",
            "A customer invoice must offer sale journals, whatever the "
            "category's account_move_type says",
        )
        self.assertTrue(
            self.env["account.journal"].search_count(
                [
                    ("type", "=", request.journal_type),
                    ("id", "=", request.journal_id.id),
                ],
            ),
            "The journal stored on the request must satisfy the field's own domain",
        )

    def test_account_move_type_is_not_an_applicability_criterion(self):
        category = self._new_category(
            name="Bills only",
            move_amount_min=100.0,
            account_move_type="in_invoice",
        )

        self.assertTrue(
            category._is_applicable_for(self._new_move("out_invoice", price=5000.0)),
            "account_move_type drives the creation flow, not applicability — "
            "if this ever becomes a criterion, the manifest has to say so",
        )

    def test_shipped_collection_in_kind_category_is_payable(self):
        category = self.env.ref(
            "approval_account.approval_category_collection_in_kind",
        )

        self.assertEqual(category.approval_type, "payment")

        request = self.env["approval.request"].create(
            {
                "name": "In kind",
                "category_id": category.id,
                "request_owner_id": self.env.uid,
                "partner_id": self.partner_a.id,
                "amount": 500.0,
                "date": "2026-06-01",
            },
        )
        self.assertTrue(
            request.is_payable,
            "The shipped payment category has to reach Treasury > To Pay",
        )

    def test_approval_notes_reach_the_approver(self):
        self.partner_a.invoice_approval_notes = "Verify credit terms"
        move = self._new_move(move_type="in_invoice", price=900.0)
        move.journal_id.approval_notes = "Check the exchange rate"

        reason = move._get_approval_reason_html()

        self.assertIn("Verify credit terms", reason)
        self.assertIn("Check the exchange rate", reason)

    def test_journal_entry_list_view_reference_resolves(self):
        self.assertTrue(
            self.env.ref("account.view_move_tree", raise_if_not_found=False)
        )

    def test_global_category_thresholds_carry_a_currency(self):
        category = self._new_category(
            name="Global amount",
            company_id=False,
            move_amount_min=1000.0,
        )

        self.assertFalse(category.company_id)
        self.assertEqual(
            category.move_amount_currency_id,
            self.env.company.currency_id,
            "A global category must fall back to the active company's currency "
            "instead of leaving the thresholds currency-less",
        )

    def test_approved_amount_is_compared_across_currencies(self):
        other_currency = self.setup_other_currency("EUR")
        self.partner_a.invoice_approval_required = True
        move = self._approved_move(price=1000.0)
        self.assertEqual(move.approval_request_id.amount, 1000.0)
        self.assertNotEqual(other_currency, move.currency_id)

        move.currency_id = other_currency

        self.assertTrue(
            move.approval_required,
            "the partner flag must keep the requirement on, so this case "
            "exercises the comparison and not the fallback below",
        )
        move.action_post()
        self.assertEqual(move.state, "draft")
        self.assertEqual(move.approval_state, "pending", "asked again")

    def test_approved_move_is_rechecked_after_falling_out_of_range(self):
        other_currency = self.setup_other_currency("EUR")
        move = self._approved_move(price=1000.0)
        self.assertEqual(move.approval_request_id.amount, 1000.0)

        move.currency_id = other_currency

        self.assertFalse(
            move.approval_required,
            "the swap is expected to drop the move below the category range",
        )
        move.action_post()
        self.assertEqual(move.state, "draft")
        self.assertEqual(move.approval_state, "pending", "asked again")

    def test_approved_amount_error_labels_each_currency(self):
        other_currency = self.setup_other_currency("EUR")
        move = self._approved_move(price=1000.0)
        request_currency = move.approval_request_id.currency_id
        self.assertNotEqual(request_currency, other_currency)

        move.currency_id = other_currency
        move.invoice_line_ids[0].price_unit = 9999.0

        with self.assertRaises(UserError) as capture:
            move._check_approved_amount()

        message = str(capture.exception)
        self.assertIn(
            f"Approved amount: {request_currency.symbol}",
            message,
            "The approved amount must be labelled in the currency it was "
            "approved in, not in the move's current one",
        )
        self.assertIn(f"Current amount: {other_currency.symbol}", message)

    def test_shipped_accounting_categories_are_global(self):
        for xmlid in (
            "approval_account.approval_category_account_move",
            "approval_account.approval_category_accounting_request",
        ):
            category = self.env.ref(xmlid)
            self.assertFalse(
                category.company_id,
                f"{xmlid} must stay global — the runtime lookup filters on "
                "company_id in (move company, False), so a pinned category is "
                "invisible in every other company",
            )

    def test_flagged_partner_reaches_the_shipped_category(self):
        shipped = self.env.ref("approval_account.approval_category_account_move")
        shipped._add_approver(self.approver, required=True)
        self.partner_a.bill_approval_required = True

        move = self._new_move(move_type="in_invoice", price=500.0)

        self.assertTrue(move.approval_required)
        move.action_create_approval_request()
        self.assertEqual(move.approval_request_id.category_id, shipped)

    def test_missing_category_error_names_the_company(self):
        move = self._new_move()

        with self.assertRaises(UserError) as capture:
            move._raise_approval_category_not_configured()

        self.assertIn(move.company_id.display_name, str(capture.exception))

    def test_approval_subtypes_are_internal(self):
        approved = self.env.ref("approval_account.mt_invoice_approved")
        refused = self.env.ref("approval_account.mt_invoice_refused")
        self.assertTrue(approved.internal)
        self.assertTrue(refused.internal)

        _default, internal, external = self.env[
            "mail.message.subtype"
        ].default_subtypes("account.move")
        for subtype in (approved, refused):
            self.assertIn(subtype, internal)
            self.assertNotIn(subtype, external)

    def test_external_follower_is_not_notified_of_an_approval(self):
        move = self._approved_move(price=1000.0)
        customer = self.env["res.partner"].create(
            {"name": "External follower", "email": "external@test.com"},
        )
        self.assertTrue(customer.partner_share)
        move.message_subscribe(partner_ids=customer.ids)
        follower = self.env["mail.followers"].search(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "=", move.id),
                ("partner_id", "=", customer.id),
            ],
        )
        self.assertTrue(follower)
        self.assertNotIn(
            self.env.ref("approval_account.mt_invoice_approved"),
            follower.subtype_ids,
        )

        before = self.env["mail.message"].search(
            [("model", "=", "account.move"), ("res_id", "=", move.id)],
        )
        move._on_approval_approved()
        posted = self.env["mail.message"].search(
            [
                ("model", "=", "account.move"),
                ("res_id", "=", move.id),
                ("id", "not in", before.ids),
            ],
        )
        self.assertTrue(posted)
        self.assertNotIn(customer, posted.mapped("notified_partner_ids"))

    def test_partner_approval_page_does_not_need_a_rank(self):
        partner_id, _label = self.env["res.partner"].name_create("Brand new vendor")
        partner = self.env["res.partner"].browse(partner_id)
        self.assertFalse(partner.customer_rank)
        self.assertFalse(partner.supplier_rank)

        arch = self.env["res.partner"].get_view(
            self.env.ref("base.view_partner_form").id,
            "form",
        )
        tree = etree.fromstring(arch["arch"])
        for name in (
            "invoice_approval_required",
            "bill_approval_required",
            "invoice_approval_notes",
        ):
            widgets = tree.xpath(f"//field[@name='{name}']")
            self.assertTrue(widgets, f"{name} must be in the arch")
            for node in [widgets[0], *widgets[0].iterancestors()]:
                modifier = node.get("invisible") or ""
                self.assertNotIn("customer_rank", modifier)
                self.assertNotIn("supplier_rank", modifier)

        partner.bill_approval_required = True
        self.assertTrue(partner.bill_approval_required)

    def test_accounting_only_category_fields_are_gated(self):
        arch = self.env["approval.category"].get_view(
            self.env.ref("approval.view_approval_category_form").id,
            "form",
        )
        tree = etree.fromstring(arch["arch"])
        for name in ("has_bsl", "has_journal"):
            nodes = tree.xpath(f"//field[@name='{name}']")
            self.assertTrue(nodes, f"{name} must be in the arch")
            gates = []
            node = nodes[0]
            while node is not None:
                if node.get("invisible"):
                    gates.append(node.get("invisible"))
                node = node.getparent()
            self.assertTrue(
                gates,
                f"{name} is accounting-only and must be gated: neither the "
                "field nor any ancestor carries an invisible",
            )

    def test_global_category_range_ignores_the_reader_company(self):
        other_currency = self.setup_other_currency("EUR")
        other_company = self.setup_other_company(name="regression_co2")["company"]
        other_company.currency_id = other_currency
        category = self._new_category(
            name="Global range",
            company_id=False,
            move_amount_min=1000.0,
        )
        self.env.user.company_ids |= other_company
        home = self.env(
            context=dict(
                self.env.context,
                allowed_company_ids=[self.env.company.id, other_company.id],
            ),
        )
        away = self.env(
            context=dict(
                self.env.context,
                allowed_company_ids=[other_company.id, self.env.company.id],
            ),
        )

        for price in (400.0, 700.0, 1000.0, 1500.0):
            move = self._new_move(move_type="in_invoice", price=price)
            self.assertEqual(
                category.with_env(home)._move_amount_range_in(move.company_id, move),
                category.with_env(away)._move_amount_range_in(move.company_id, move),
                f"the range for a {price} move must not depend on the reader",
            )
            self.assertEqual(
                category.with_env(home)._is_applicable_for(move.with_env(home)),
                category.with_env(away)._is_applicable_for(move.with_env(away)),
                f"applicability for a {price} move must not depend on the reader",
            )

    def test_bank_statement_line_request_fields_have_distinct_labels(self):
        fields_ = self.env["account.bank.statement.line"]._fields
        self.assertNotEqual(
            fields_["approval_request_id"].string,
            fields_["approval_request_ids"].string,
        )

    def test_payment_state_has_a_bulk_action_in_both_directions(self):
        actions = self.env["ir.actions.server"].search(
            [("binding_model_id.model", "=", "approval.request")],
        )
        codes = " ".join(actions.mapped("code"))
        self.assertIn("action_mark_paid", codes)
        self.assertIn("action_mark_not_paid", codes)

        treasury = self.env.ref("approval_account.group_treasury_payment")
        for xmlid in (
            "approval_account.action_approval_request_mark_paid",
            "approval_account.action_approval_request_mark_not_paid",
        ):
            self.assertIn(
                treasury,
                self.env.ref(xmlid).group_ids,
                f"{xmlid} must stay gated on Release Payments",
            )

    def test_accounting_groups_keep_their_approval_access(self):
        billing = self.env["res.users"].create(
            {
                "name": "ACL billing user",
                "login": "acl_billing_user",
                "group_ids": [(6, 0, [self.env.ref("account.group_account_user").id])],
            },
        )
        manager = self.env["res.users"].create(
            {
                "name": "ACL accounting manager",
                "login": "acl_accounting_manager",
                "group_ids": [
                    (6, 0, [self.env.ref("account.group_account_manager").id]),
                ],
            },
        )
        self.assertTrue(billing.has_group("base.group_user"))
        self.assertTrue(manager.has_group("base.group_user"))

        category = self._new_category(name="ACL category")
        request = (
            self.env["approval.request"]
            .with_user(billing)
            .create(
                {
                    "name": "ACL request",
                    "category_id": category.id,
                    "date": "2026-06-01",
                },
            )
        )
        request.with_user(billing).write({"name": "ACL request renamed"})
        self.assertEqual(request.with_user(billing).name, "ACL request renamed")

        self.env["approval.category"].with_user(manager).create(
            {
                "name": "ACL manager category",
                "approval_type": "accounting",
                "approval_minimum": 1,
            },
        )

    def test_settings_button_reuses_the_category_action(self):
        menu_action = self.env.ref(
            "approval_account.action_approval_category_accounting",
        )
        button_action = (
            self.env["res.config.settings"]
            .create(
                {},
            )
            .action_view_invoice_approval_categories()
        )

        self.assertEqual(button_action["res_model"], "approval.category")
        self.assertEqual(button_action["id"], menu_action.id)
        self.assertNotIn("default_company_id", button_action.get("context") or {})

        global_category = self._new_category(
            name="Global for the button",
            company_id=False,
        )
        domain = button_action["domain"]
        if isinstance(domain, str):
            domain = literal_eval(domain)
        matched = self.env["approval.category"].search(domain or [])
        self.assertIn(
            global_category,
            matched,
            "the button must not drop global categories the way its own "
            "hand-rolled domain did",
        )

    def test_count_approval_follows_its_declared_depends(self):
        category = self._new_category(name="Count category")
        request = self.env["approval.request"].create(
            {
                "name": "Count request",
                "category_id": category.id,
                "partner_id": self.partner_a.id,
                "date": "2026-06-01",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "product_uom_id": self.product.uom_id.id,
                        },
                    ),
                ],
            },
        )
        move = self._new_move(move_type="in_invoice", price=100.0)
        line = move.invoice_line_ids[0]
        self.assertEqual(move.count_approval, 0)

        request.line_ids[0].account_move_line_id = line
        self.assertEqual(
            move.count_approval,
            len(move.line_ids.approval_request_line_id.approval_request_id),
        )

        line.approval_request_line_id = request.line_ids[0]
        self.assertEqual(move.count_approval, 1)

    def test_one_approval_stat_button_for_a_single_request(self):
        category = self._new_category(
            name="Stat button category",
            target_model="account.move",
            account_move_type="in_invoice",
            has_product="required",
            has_quantity="required",
            has_partner="required",
        )
        request = self.env["approval.request"].create(
            {
                "name": "Stat button request",
                "category_id": category.id,
                "partner_id": self.partner_a.id,
                "date": "2026-06-01",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "product_uom_id": self.product.uom_id.id,
                        },
                    ),
                ],
            },
        )
        request.action_confirm()
        request.with_user(self.approver).action_approve()
        request.action_create_account_moves()
        move = request.line_ids.account_move_line_id.move_id

        self.assertTrue(move.approval_request_id)
        self.assertEqual(move.count_approval, 1)
        request_button = bool(move.approval_request_id)
        count_button = move.count_approval != 0 and not (
            move.count_approval == 1 and move.approval_request_id
        )
        self.assertFalse(
            request_button and count_button,
            "a move belonging to one request must render one Approval button",
        )

    def test_request_move_count_follows_a_mixin_link(self):
        category = self._new_category(name="Count moves category")
        request = self.env["approval.request"].create(
            {
                "name": "Count moves request",
                "category_id": category.id,
                "partner_id": self.partner_a.id,
                "date": "2026-06-01",
            },
        )
        self.assertEqual(request.count_account_move, 0)

        move = self._new_move(move_type="in_invoice", price=100.0)
        move.sudo().write({"approval_request_id": request.id})

        self.assertEqual(
            request.count_account_move,
            1,
            "linking a move the mixin way must invalidate the count without "
            "an explicit invalidate_recordset()",
        )

    def test_second_company_invoice_reaches_an_approval_request(self):
        company_2 = self.company_2
        company_2.bill_approval_threshold = 100.0
        self.approver.company_ids |= company_2
        shipped = self.env.ref("approval_account.approval_category_account_move")
        shipped._add_approver(self.approver, required=True)
        journal = self.env["account.journal"].search(
            [("company_id", "=", company_2.id), ("type", "=", "purchase")],
            limit=1,
        )
        move = (
            self.env["account.move"]
            .with_company(company_2)
            .create(
                {
                    "move_type": "in_invoice",
                    "company_id": company_2.id,
                    "journal_id": journal.id,
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2026-06-01",
                    "date": "2026-06-01",
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "quantity": 1.0,
                                "price_unit": 500.0,
                                "tax_ids": [],
                            },
                        ),
                    ],
                },
            )
        )

        self.assertEqual(move.company_id, company_2)
        self.assertTrue(
            move.approval_required,
            "500 is above this company's own 100 threshold",
        )
        move.action_create_approval_request()
        self.assertTrue(move.approval_request_id)
        self.assertEqual(move.approval_request_id.company_id, company_2)

    def test_auto_post_posts_the_move_when_approval_is_granted(self):
        self.category_amount.move_auto_post = True
        move = self._new_move(price=1000.0)
        move.action_create_approval_request()
        self.assertEqual(move.approval_request_id.category_id, self.category_amount)

        move.approval_request_id.with_user(self.approver).action_approve()

        self.assertEqual(move.state, "posted")

    def test_auto_post_failure_becomes_a_chatter_note(self):
        self.category_amount.move_auto_post = True
        move = self._new_move(price=1000.0)
        move.action_create_approval_request()
        self.env.company.account_config_id.fiscalyear_lock_date = "2026-12-31"

        move.approval_request_id.with_user(self.approver).action_approve()

        self.assertEqual(move.approval_state, "approved")
        self.assertEqual(move.state, "draft")
        notes = move.message_ids.filtered(
            lambda message: "could not be auto-posted" in (message.body or ""),
        )
        self.assertTrue(
            notes,
            "the post failure must be swallowed into a chatter note rather "
            "than raised out of the approval",
        )

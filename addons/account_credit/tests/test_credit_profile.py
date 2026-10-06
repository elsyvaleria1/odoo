from datetime import timedelta

from psycopg.errors import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Date
from odoo.tests.common import TransactionCase, tagged

from .common import book_payment_entries


@tagged("post_install", "-at_install")
class CreditProfileCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "approval.category" in cls.env:
            cls.env["approval.category"].search([("approval_type", "=", "sale")]).write(
                {"active": False}
            )
        if "so_validation_level" in cls.env["res.company"]._fields:
            cls.env.company.so_validation_level = "none"
        cls.config = cls.env["credit.config"]._for(cls.env.company)
        cls.config.write(
            {"watch_days": 30, "default_days": 90, "exception_max_days": 60}
        )
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Profile Product", "list_price": 1000.0}
        )
        book_payment_entries(cls.env)
        cls.term_30 = cls.env["account.payment.term"].create(
            {
                "name": "Profile 30",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100.0, "nb_days": 30}
                    )
                ],
            }
        )
        cls.reliable = cls.env.ref("account_credit.credit_grade_reliable")
        cls.preferred = cls.env.ref("account_credit.credit_grade_preferred")
        cls.default = cls.env.ref("account_credit.credit_grade_default")
        cls.cash = cls.env.ref("account_credit.credit_grade_cash")
        cls.unconditional = cls.env["credit.grade"].create(
            {"name": "Profile Unconditional"}
        )
        cls.short_term = cls.env["credit.grade"].create(
            {"name": "Profile Short Term", "max_payment_term_days": 60}
        )

    def _partner(self, name, **vals):
        return self.env["res.partner"].create(
            {"name": name, "is_company": True, **vals}
        )

    def _profile(self, partner):
        return self.env["credit.profile"]._for_partner(partner, create=True)

    def _invoice(self, partner, amount, days_ago, due_days_ago=None, post=True):
        due = Date.today() - timedelta(
            days=due_days_ago if due_days_ago is not None else days_ago
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "journal_id": self.journal.id,
                "invoice_date": Date.today() - timedelta(days=days_ago),
                "invoice_date_due": due,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        if post:
            invoice.with_context(credit_override=True).action_post()
        return invoice

    def _pay(self, invoice, days_ago):
        self.env["wizard.account.move.line.pay"].with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create(
            {"payment_date": Date.today() - timedelta(days=days_ago)}
        )._create_payments()

    def _order(self, partner, amount, term=None):
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "payment_term_id": (term or self.term_30).id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1,
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )


class TestProfileLifecycle(CreditProfileCase):
    def test_a_new_partner_has_no_profile_until_credit_is_asked(self):
        partner = self._partner("Fresh")
        self.assertFalse(partner.sudo().credit_profile_id)
        self.assertFalse(partner.credit_status)
        partner.credit_grade_id = self.unconditional
        profile = partner.sudo().credit_profile_id
        self.assertTrue(profile)
        self.assertEqual(profile.company_id, self.env.company)
        self.assertEqual(profile.state, "active")

    def test_the_entry_grade_is_cash_only(self):
        partner = self._partner("Entry")
        profile = self._profile(partner)
        self.assertEqual(profile.grade_id, self.config.entry_grade_id)
        self.assertEqual(profile.state, "cash")
        with self.assertRaises(ValidationError):
            self._order(partner, 100.0).action_confirm()

    def test_one_profile_per_partner_and_company(self):
        partner = self._partner("Unique")
        self._profile(partner)
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.env["credit.profile"].create(
                    {"partner_id": partner.id, "company_id": self.env.company.id}
                )

    def test_a_contact_reads_its_company_profile(self):
        company = self._partner("Family", credit_grade_id=self.unconditional.id)
        contact = self.env["res.partner"].create(
            {"name": "Child", "parent_id": company.id, "type": "invoice"}
        )
        self.assertEqual(
            contact.sudo().credit_profile_id, company.sudo().credit_profile_id
        )
        self.assertEqual(contact.credit_grade_id, self.unconditional)

    def test_only_a_credit_user_changes_the_grade(self):
        partner = self._partner("Guarded", credit_grade_id=self.unconditional.id)
        user = self.env["res.users"].create(
            {
                "name": "plain",
                "login": "credit_profile_plain",
                "group_ids": [Command.link(self.env.ref("base.group_user").id)],
            }
        )
        with self.assertRaises(AccessError):
            partner.with_user(user).write({"credit_grade_id": self.preferred.id})


class TestExceptionsAreDated(CreditProfileCase):
    def test_an_exception_always_carries_an_end(self):
        partner = self._partner("Dated", credit_exception=True)
        profile = partner.sudo().credit_profile_id
        self.assertEqual(
            profile.exception_until,
            Date.today() + timedelta(days=self.config.exception_max_days),
        )
        self.assertTrue(profile.exception_active)
        self.assertEqual(partner.credit_status, "authorized")

    def test_an_exception_cannot_outlive_the_company_maximum(self):
        profile = self._profile(self._partner("Too long"))
        with self.assertRaises(ValidationError):
            profile.write(
                {
                    "exception_until": Date.today()
                    + timedelta(days=self.config.exception_max_days + 1)
                }
            )

    def test_an_expired_exception_is_recorded_and_reviewed(self):
        partner = self._partner("Expiring", credit_exception=True)
        profile = partner.sudo().credit_profile_id
        profile.write({"exception_until": Date.today() - timedelta(days=1)})
        self.assertFalse(profile.exception_active)
        profile._expire_exceptions()
        self.assertFalse(profile.exception_until)
        self.assertTrue(profile._open_events("exception_expired"))
        self.assertTrue(
            profile.review_ids.filtered(lambda r: r.state in ("draft", "in_progress"))
        )

    def test_the_wizard_opens_a_reclassification_review(self):
        profile = self._profile(self._partner("Wizard"))
        wizard = self.env["wizard.credit.profile.grant.exception"].create(
            {"profile_id": profile.id, "reason": "legacy customer"}
        )
        self.assertEqual(wizard.max_days, self.config.exception_max_days)
        wizard.action_grant()
        self.assertTrue(profile.exception_active)
        review = profile.review_ids
        self.assertEqual(review.kind, "exception")
        self.assertEqual(review.state, "draft")

    def test_a_running_exception_allows_credit_without_approval(self):
        partner = self._partner("Allowed", credit_exception=True)
        order = self._order(partner, 500.0)
        verdict = order._credit_verdict()
        self.assertEqual(verdict.outcome, "allow")
        self.assertIn("exception_active", verdict.conditions)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_a_hold_ends_the_exception(self):
        partner = self._partner("Held", credit_exception=True)
        profile = partner.sudo().credit_profile_id
        profile.action_toggle_legal()
        self.assertFalse(profile.exception_active)
        self.assertEqual(profile.state, "legal")
        with self.assertRaises(ValidationError):
            profile.write({"exception_until": Date.today() + timedelta(days=5)})


class TestMetricsAndScore(CreditProfileCase):
    def test_days_beyond_terms_is_weighted_by_amount(self):
        partner = self._partner("Payer", credit_grade_id=self.unconditional.id)
        early = self._invoice(partner, 1000.0, days_ago=100, due_days_ago=70)
        self._pay(early, days_ago=80)
        late = self._invoice(partner, 3000.0, days_ago=100, due_days_ago=70)
        self._pay(late, days_ago=30)
        profile = partner.sudo().credit_profile_id
        profile._update_metrics()
        self.assertAlmostEqual(
            profile.dbt_weighted, (-10 * 1000 + 40 * 3000) / 4000, places=1
        )
        self.assertAlmostEqual(profile.late_ratio, 75.0, places=1)
        self.assertEqual(profile.max_days_late, 40)
        self.assertEqual(profile.purchases_12m, 4000.0)
        self.assertGreaterEqual(profile.tenure_months, 3)

    def test_the_scorecard_proposes_a_grade(self):
        partner = self._partner("Scored", credit_grade_id=self.unconditional.id)
        invoice = self._invoice(partner, 1000.0, days_ago=60, due_days_ago=30)
        self._pay(invoice, days_ago=35)
        profile = partner.sudo().credit_profile_id
        profile._update_metrics()
        self.assertTrue(profile.score_line_ids)
        self.assertGreater(profile.score, 0.0)
        self.assertTrue(profile.grade_proposed_id)
        self.assertEqual(
            profile.grade_proposed_id,
            self.env["credit.grade"]._classify(profile.score, profile.company_id),
        )

    def test_every_score_between_0_and_100_proposes_a_grade(self):
        Grade = self.env["credit.grade"]
        for score, code in (
            (0.0, "default"),
            (34.99, "default"),
            (35.0, "restricted"),
            (49.5, "restricted"),
            (50.0, "watch"),
            (64.5, "watch"),
            (65.0, "reliable"),
            (79.09, "reliable"),
            (79.99, "reliable"),
            (80.0, "preferred"),
            (100.0, "preferred"),
        ):
            self.assertEqual(Grade._classify(score, self.env.company).code, code, score)
        partner = self._partner("Fractional", credit_grade_id=self.unconditional.id)
        profile = partner.sudo().credit_profile_id
        profile.write({"score": 79.5, "metrics_date": Date.today()})
        self.assertEqual(profile.grade_proposed_id.code, "reliable")

    def test_a_grade_without_a_range_is_never_proposed(self):
        Grade = self.env["credit.grade"]
        rangeless = Grade.create({"name": "Rangeless"})
        self.assertFalse(rangeless._is_band())
        self.assertNotIn(
            rangeless,
            [Grade._classify(s, self.env.company) for s in (0.0, 50.0, 100.0)],
        )
        with self.assertRaises(ValidationError):
            Grade.create({"name": "Overlapping", "min_value": 60, "max_value": 70})

    def test_an_old_overdue_puts_the_profile_in_default(self):
        partner = self._partner("Defaulting", credit_grade_id=self.unconditional.id)
        self._invoice(partner, 5000.0, days_ago=200, due_days_ago=120)
        profile = partner.sudo().credit_profile_id
        profile._update_metrics()
        self.assertGreaterEqual(profile.oldest_open_days, 120)
        self.assertEqual(profile.state, "default")
        self.assertEqual(partner.credit_status, "default")
        profile._detect_events()
        self.assertTrue(profile._open_events("overdue_default"))
        self.assertEqual(profile.grade_effective_id, self.default)
        verdict = self._order(partner, 100.0)._credit_verdict()
        self.assertEqual(verdict.outcome, "approve")
        self.assertIn("state_is", verdict.conditions)

    def test_settling_the_default_lifts_it(self):
        partner = self._partner("Recovering", credit_grade_id=self.unconditional.id)
        invoice = self._invoice(partner, 5000.0, days_ago=200, due_days_ago=120)
        profile = partner.sudo().credit_profile_id
        profile._update_metrics()
        profile._detect_events()
        self.assertTrue(profile._open_events("overdue_default"))
        self._pay(invoice, days_ago=0)
        profile._update_metrics()
        profile._detect_events()
        self.assertFalse(profile._open_events("overdue_default"))
        self.assertTrue(
            profile.event_ids.filtered(lambda e: e.code == "payment_recovered")
        )
        self.assertNotEqual(profile.state, "default")
        self.assertNotEqual(
            profile.grade_id.kind,
            "default",
            "a default is a fact of the ledger, never an automatically decided grade",
        )

    def test_a_worse_proposal_lowers_the_grade_automatically(self):
        partner = self._partner("Sliding", credit_grade_id=self.preferred.id)
        paid = self._invoice(partner, 1000.0, days_ago=60, due_days_ago=30)
        self._pay(paid, days_ago=30)
        self._invoice(partner, 5000.0, days_ago=50, due_days_ago=20)
        profile = partner.sudo().credit_profile_id
        profile._update_metrics()
        profile._detect_events()
        self.assertGreater(profile.grade_id.sequence, self.preferred.sequence)
        self.assertNotEqual(profile.grade_id.kind, "default")
        self.assertTrue(profile.event_ids.filtered(lambda e: e.code == "grade_changed"))

    def test_a_better_proposal_waits_for_a_review(self):
        partner = self._partner("Climbing", credit_grade_id=self.reliable.id)
        paid = self._invoice(partner, 1000.0, days_ago=60, due_days_ago=30)
        self._pay(paid, days_ago=40)
        profile = partner.sudo().credit_profile_id
        profile._update_metrics()
        profile._detect_events()
        self.assertEqual(profile.grade_id, self.reliable)


class TestExternalComponents(CreditProfileCase):
    def test_the_z_score_follows_altman_four_ratios(self):
        partner = self._partner("Statements", credit_grade_id=self.unconditional.id)
        profile = partner.sudo().credit_profile_id
        profile.write(
            {
                "fin_total_assets": 1000.0,
                "fin_current_assets": 500.0,
                "fin_current_liabilities": 300.0,
                "fin_total_liabilities": 400.0,
                "fin_retained_earnings": 200.0,
                "fin_ebit": 100.0,
                "fin_equity_book": 600.0,
            }
        )
        expected = 6.56 * 0.2 + 3.26 * 0.2 + 6.72 * 0.1 + 1.05 * 1.5
        self.assertAlmostEqual(profile.z_score, expected, places=2)
        profile._score_refresh()
        line = profile.score_line_ids.filtered(lambda l: l.dimension_code == "z_score")
        self.assertTrue(line)
        self.assertGreater(profile.z_score, 4.0, "well inside Altman's safe zone")
        self.assertEqual(line.points, line.max_points)
        profile.write({"fin_ebit": -300.0, "fin_retained_earnings": -100.0})
        self.assertLess(profile.z_score, 1.1, "distress zone")
        profile._score_refresh()
        line = profile.score_line_ids.filtered(lambda l: l.dimension_code == "z_score")
        self.assertEqual(line.points, 0.0)
        self.assertTrue(line.applicable)

    def test_components_without_data_do_not_count(self):
        partner = self._partner("No bureau", credit_grade_id=self.unconditional.id)
        profile = partner.sudo().credit_profile_id
        profile._score_refresh()
        rows = profile.score_line_ids
        skipped = rows.filtered(lambda l: not l.applicable)
        # A subset: a bridge may add dimensions of its own that skip here too.
        self.assertLessEqual(
            {"dbt", "late_ratio", "bureau_score", "z_score"},
            set(skipped.mapped("dimension_code")),
            "no payment history, no bureau, no statements: those leave the denominator",
        )
        self.assertEqual(
            profile.score_max_points,
            sum(rows.filtered("applicable").mapped("max_points")),
        )
        profile.bureau_score = 700
        profile._score_refresh()
        line = profile.score_line_ids.filtered(
            lambda l: l.dimension_code == "bureau_score"
        )
        self.assertTrue(line.applicable)
        self.assertEqual(line.points, 0.85 * line.max_points)
        self.assertEqual(line.max_points, 10.0)

    def test_an_observation_on_a_bound_keeps_its_band(self):
        # 127 of 395 production customers pay on the due date: dbt exactly 0
        # is the top band, and a value on any converted bound lands where the
        # old inclusive bound put it.
        partner = self._partner("On the bound", credit_grade_id=self.unconditional.id)
        profile = partner.sudo().credit_profile_id
        Dimension = self.env["scorecard.dimension"]
        dbt = Dimension.search([("code", "=", "dbt")], limit=1)
        oldest = Dimension.search([("code", "=", "oldest_open_days")], limit=1)
        for dbt_value, dbt_share in ((0.0, 1.0), (-3.0, 1.0), (15.0, 0.8), (15.1, 0.6)):
            profile.write({"paid_12m": 1000.0, "dbt_weighted": dbt_value})
            profile._score_refresh()
            line = profile.score_line_ids.filtered(lambda l: l.dimension_code == "dbt")
            self.assertAlmostEqual(
                line.points, dbt_share * dbt.weight, places=4, msg=dbt_value
            )
        profile.write({"oldest_open_days": 0})
        profile._score_refresh()
        line = profile.score_line_ids.filtered(
            lambda l: l.dimension_code == "oldest_open_days"
        )
        self.assertEqual(line.points, oldest.weight)

    def test_a_grade_change_records_both_grades(self):
        partner = self._partner("Moved", credit_grade_id=self.reliable.id)
        profile = partner.sudo().credit_profile_id
        profile.write({"grade_id": self.preferred.id})
        event = profile.event_ids.filtered(lambda e: e.code == "grade_changed")[:1]
        self.assertEqual(event.grade_from_id, self.reliable)
        self.assertEqual(event.grade_to_id, self.preferred)


class TestReviews(CreditProfileCase):
    def test_an_approved_review_sets_grade_facility_and_next_date(self):
        partner = self._partner("Reviewed", credit_grade_id=self.unconditional.id)
        profile = partner.sudo().credit_profile_id
        review = profile._open_review("manual")
        review.write(
            {
                "grade_decided_id": self.preferred.id,
                "limit_decided": 25000.0,
                "facility_months": 6,
            }
        )
        review.action_approve()
        self.assertEqual(review.state, "approved")
        self.assertEqual(profile.grade_id, self.preferred)
        facility = profile.facility_ids.filtered(lambda f: f.state == "active")
        self.assertEqual(facility.amount, 25000.0)
        self.assertEqual(facility.source, "grade")
        self.assertEqual(profile.limit_amount, 25000.0)
        self.assertEqual(partner.credit_limit, 25000.0)
        self.assertTrue(profile.next_review_date)
        self.assertFalse(profile.exception_until)

    def test_a_review_replaces_the_previous_manual_line(self):
        partner = self._partner(
            "Replaced",
            credit_grade_id=self.unconditional.id,
            credit_trusted_amount=5000.0,
        )
        profile = partner.sudo().credit_profile_id
        self.assertEqual(profile.limit_amount, 5000.0)
        review = profile._open_review("manual")
        review.write({"grade_decided_id": self.reliable.id, "limit_decided": 8000.0})
        review.action_approve()
        self.assertEqual(profile.limit_amount, 8000.0)

    def test_reviews_are_approved_in_batch_as_proposed(self):
        partners = [
            self._partner(f"Batch {i}", credit_grade_id=self.unconditional.id)
            for i in range(3)
        ]
        reviews = self.env["credit.review"]
        for partner in partners:
            paid = self._invoice(partner, 1000.0, days_ago=60, due_days_ago=30)
            self._pay(paid, days_ago=35)
            reviews |= partner.sudo().credit_profile_id._open_review("exception")
        reviews.action_refresh()
        self.assertTrue(all(reviews.mapped("grade_proposed_id")))
        reviews.action_approve_proposed()
        self.assertEqual(set(reviews.mapped("state")), {"approved"})
        for review in reviews:
            self.assertEqual(review.profile_id.grade_id, review.grade_proposed_id)
            self.assertTrue(review.profile_id.next_review_date)

    def test_only_one_review_is_open_at_a_time(self):
        profile = self._profile(self._partner("Once"))
        first = profile._open_review("manual")
        second = profile._open_review("periodic")
        self.assertEqual(first, second)

    def test_a_due_review_is_scheduled_by_the_cron(self):
        partner = self._partner("Due", credit_grade_id=self.unconditional.id)
        profile = partner.sudo().credit_profile_id
        profile.next_review_date = Date.today() - timedelta(days=1)
        profile._schedule_reviews()
        self.assertEqual(profile.review_ids.kind, "periodic")

    def test_only_a_manager_decides(self):
        profile = self._profile(self._partner("Decided"))
        review = profile._open_review("manual")
        user = self.env["res.users"].create(
            {
                "name": "credit user",
                "login": "credit_profile_user",
                "group_ids": [
                    Command.link(self.env.ref("account_credit.group_credit_user").id)
                ],
            }
        )
        with self.assertRaises(UserError):
            review.with_user(user).action_approve()


class TestFacilities(CreditProfileCase):
    def test_an_expired_facility_stops_granting(self):
        partner = self._partner("Expired", credit_grade_id=self.unconditional.id)
        profile = partner.sudo().credit_profile_id
        facility = self.env["credit.facility"].create(
            {
                "profile_id": profile.id,
                "amount": 3000.0,
                "date_start": Date.today() - timedelta(days=40),
                "date_end": Date.today() - timedelta(days=1),
            }
        )
        self.assertEqual(profile.limit_amount, 0.0)
        self.env["credit.facility"]._cron_expire()
        self.assertEqual(facility.state, "expired")
        self.assertTrue(
            profile.event_ids.filtered(lambda e: e.code == "facility_expired")
        )

    def test_a_revoked_line_is_kept_for_the_record(self):
        partner = self._partner("Revoked", credit_grade_id=self.unconditional.id)
        profile = partner.sudo().credit_profile_id
        facility = self.env["credit.facility"].create(
            {"profile_id": profile.id, "amount": 3000.0}
        )
        self.assertEqual(partner.credit_limit, 3000.0)
        facility.action_revoke()
        self.assertEqual(facility.state, "revoked")
        self.assertTrue(facility.exists())
        partner.invalidate_recordset(["credit_limit"])
        self.assertEqual(partner.credit_limit, 0.0)


class TestPolicy(CreditProfileCase):
    def test_rules_are_read_in_order_and_a_stop_rule_ends_the_walk(self):
        partner = self._partner("Ordered", credit_grade_id=self.unconditional.id)
        self._invoice(partner, 1000.0, days_ago=50, due_days_ago=20)
        profile = partner.sudo().credit_profile_id
        verdict = profile._evaluate(
            "order", amount=100.0, immediate=False, term_days=30
        )
        self.assertEqual(verdict.outcome, "approve")
        self.assertIn("overdue_amount_over", verdict.conditions)
        profile.write(
            {
                "exception_until": Date.today() + timedelta(days=10),
                "exception_reason": "x",
            }
        )
        verdict = profile._evaluate(
            "order", amount=100.0, immediate=False, term_days=30
        )
        self.assertEqual(verdict.outcome, "allow")
        self.assertEqual(verdict.conditions, ["exception_active"])

    def test_a_term_longer_than_the_grade_allows_needs_authorization(self):
        partner = self._partner("Long term", credit_grade_id=self.short_term.id)
        profile = partner.sudo().credit_profile_id
        long_term = self.env["account.payment.term"].create(
            {
                "name": "Profile 120",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100.0, "nb_days": 120}
                    )
                ],
            }
        )
        verdict = profile._evaluate(
            "order",
            amount=100.0,
            immediate=False,
            term_days=profile._term_days(long_term),
        )
        self.assertIn("term_over_max", verdict.conditions)
        self.assertEqual(verdict.outcome, "approve")

    def test_immediate_terms_bypass_credit_rules(self):
        partner = self._partner("Immediate", credit_grade_id=self.cash.id)
        profile = partner.sudo().credit_profile_id
        verdict = profile._evaluate(
            "invoice", amount=100.0, immediate=True, term_days=0
        )
        self.assertEqual(verdict.outcome, "allow")

    def test_a_company_rule_overrides_for_its_company_only(self):
        partner = self._partner("Company rule", credit_grade_id=self.unconditional.id)
        profile = partner.sudo().credit_profile_id
        rule = self.env["credit.policy.rule"].create(
            {
                "name": "Watch grades are blocked here",
                "sequence": 1,
                "company_id": self.env.company.id,
                "document_kind": "order",
                "payment_kind": "credit",
                "condition": "always",
                "grade_ids": [Command.link(self.unconditional.id)],
                "outcome": "block",
                "stop": True,
            }
        )
        self.assertTrue(
            profile._evaluate(
                "order", amount=1.0, immediate=False, term_days=30
            ).blocked
        )
        rule.active = False
        self.assertFalse(
            profile._evaluate(
                "order", amount=1.0, immediate=False, term_days=30
            ).blocked
        )


class TestDeliveries(CreditProfileCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        out_type = (
            cls.env["stock.warehouse"]
            .search([("company_id", "=", cls.env.company.id)], limit=1)
            .out_type_id
        )
        if "dispatch_batch_required" in out_type._fields:
            out_type.dispatch_batch_required = False

    def _delivery(self, partner, amount=1000.0, term=None):
        product = self.env["product.product"].create(
            {"name": "Shipped product", "list_price": amount, "is_storable": True}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "payment_term_id": (term or self.term_30).id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": 1,
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        order.with_context(credit_override=True).action_confirm()
        picking = order.picking_ids[:1]
        self.assertTrue(picking, "a storable product ships through a picking")
        return picking

    def test_a_delivery_on_credit_terms_reads_the_policy(self):
        partner = self._partner("Shipped", credit_grade_id=self.unconditional.id)
        picking = self._delivery(partner)
        self.assertTrue(picking._is_credit_delivery())
        verdict = picking._credit_verdict()
        self.assertEqual(verdict.outcome, "allow")
        self.assertEqual(picking.credit_verdict_outcome, "allow")

    def test_the_order_rules_never_hold_goods(self):
        partner = self._partner(
            "Overdue shipper", credit_grade_id=self.unconditional.id
        )
        picking = self._delivery(partner)
        self._invoice(partner, 1000.0, days_ago=50, due_days_ago=20)
        verdict = picking._credit_verdict()
        self.assertEqual(verdict.outcome, "allow")
        self.assertNotIn("overdue_amount_over", verdict.conditions)

    def test_a_profile_in_default_is_only_flagged_by_the_seed(self):
        partner = self._partner(
            "Defaulted shipper", credit_grade_id=self.unconditional.id
        )
        picking = self._delivery(partner)
        self._invoice(partner, 5000.0, days_ago=200, due_days_ago=120)
        profile = partner.sudo().credit_profile_id
        profile._update_metrics()
        self.assertEqual(profile.state, "default")
        picking.invalidate_recordset()
        self.assertEqual(picking.credit_verdict_outcome, "warn")
        self.assertIn("in default", picking.credit_verdict_message)
        picking.move_ids.write({"quantity": 1, "picked": True})
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_a_company_may_block_deliveries_by_rule(self):
        partner = self._partner(
            "Blocked shipper", credit_grade_id=self.unconditional.id
        )
        self.env.ref("account_credit.policy_rule_picking_default").write(
            {"outcome": "block"}
        )
        picking = self._delivery(partner)
        self._invoice(partner, 5000.0, days_ago=200, due_days_ago=120)
        partner.sudo().credit_profile_id._update_metrics()
        picking.move_ids.write({"quantity": 1, "picked": True})
        with self.assertRaises(ValidationError):
            picking.button_validate()
        picking.with_context(credit_override=True).button_validate()
        self.assertEqual(picking.state, "done")

    def test_a_hold_blocks_the_delivery(self):
        partner = self._partner("Held shipper", credit_grade_id=self.unconditional.id)
        picking = self._delivery(partner)
        partner.sudo().credit_profile_id.action_toggle_legal()
        picking.move_ids.write({"quantity": 1, "picked": True})
        with self.assertRaises(ValidationError):
            picking.button_validate()

    def test_an_immediate_order_ships_without_a_verdict(self):
        partner = self._partner("Cash shipper")
        immediate = self.env["account.payment.term"].create(
            {
                "name": "Delivery immediate",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100.0, "nb_days": 0}
                    )
                ],
            }
        )
        picking = self._delivery(partner, term=immediate)
        self.assertFalse(picking._is_credit_delivery())
        self.assertFalse(picking.credit_verdict_outcome)


class TestConfig(CreditProfileCase):
    def test_the_company_carries_its_credit_folder_through_the_config(self):
        folder = self.env["document.document"].create(
            {"name": "Config Root", "type": "folder"}
        )
        self.env.company.credit_folder_id = folder
        self.assertEqual(self.config.credit_folder_id, folder)
        self.assertEqual(self.env.company.credit_config_id, self.config)

    def test_thresholds_are_ordered(self):
        with self.assertRaises(ValidationError):
            self.config.write({"watch_days": 100, "default_days": 90})
        with self.assertRaises(ValidationError):
            self.config.write({"exception_max_days": 0})


class TestPortfolioReport(CreditProfileCase):
    def _refresh(self):
        self.env.flush_all()
        self.env["credit.portfolio.report"].refresh()
        self.env["credit.portfolio.report"].invalidate_model()

    def test_the_portfolio_ages_every_profile_and_prices_its_loss(self):
        partner = self._partner("Aged", credit_grade_id=self.reliable.id)
        self._invoice(partner, 1000.0, days_ago=40, due_days_ago=-10)
        self._invoice(partner, 2000.0, days_ago=80, due_days_ago=45)
        self._invoice(partner, 500.0, days_ago=300, due_days_ago=200)
        profile = partner.sudo().credit_profile_id
        self._refresh()
        row = self.env["credit.portfolio.report"].search(
            [("profile_id", "=", profile.id)]
        )
        self.assertEqual(len(row), 1)
        self.assertEqual(row.grade_id, self.reliable)
        self.assertEqual(row.amount_current, 1000.0)
        self.assertEqual(row.amount_b31_60, 2000.0)
        self.assertEqual(row.amount_b180_plus, 500.0)
        self.assertEqual(row.amount_open, 3500.0)
        self.assertEqual(row.amount_overdue, 2500.0)
        self.assertEqual(
            row.oldest_due_days,
            200,
            "aged against the ORM's UTC date, not the session's",
        )
        self.assertAlmostEqual(
            row.expected_loss, 3500.0 * self.reliable.expected_loss_rate / 100.0
        )

    def test_a_profile_without_receivables_reads_zero(self):
        partner = self._partner("Empty", credit_grade_id=self.reliable.id)
        profile = partner.sudo().credit_profile_id
        self._refresh()
        row = self.env["credit.portfolio.report"].search(
            [("profile_id", "=", profile.id)]
        )
        self.assertEqual(row.amount_open, 0.0)
        self.assertEqual(row.expected_loss, 0.0)

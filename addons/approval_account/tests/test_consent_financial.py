from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import SQL

from .common import AccountApprovalCommon
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestConsentOnFinancialVerbs(AccountApprovalCommon):
    def _category(self, name, **values):
        category = self.env["approval.category"].create(
            {
                "name": name,
                "approval_minimum": 1,
                "has_amount": "required",
                "has_partner": "required",
                **values,
            },
        )
        add_category_approver(category, self.approver, required=True)
        return category

    def _set_consent_behind_the_form(self, category, hours):
        self.env.cr.execute(
            SQL(
                "UPDATE approval_category SET consent_approval_hours = %s WHERE id = %s",
                hours,
                category.id,
            )
        )
        category.invalidate_recordset(["consent_approval_hours"])

    def _pending_request(self, category):
        request = self.env["approval.request"].create(
            {
                "name": f"Silent {category.name}",
                "category_id": category.id,
                "partner_id": self.partner_a.id,
                "amount": 100.0,
                "date": "2026-06-01",
            },
        )
        request.action_confirm()
        request.sudo().date_confirmed = fields.Datetime.now() - timedelta(hours=2)
        self.assertEqual(request.state, "pending")
        return request

    def test_consent_is_refused_on_a_category_that_posts_or_pays(self):
        for name, values in [
            ("Posting", {"approval_type": "accounting"}),
            ("Paying", {"approval_type": "payment"}),
            ("Bill", {"approval_type": "general", "target_model": "account.move"}),
        ]:
            with self.subTest(name), self.assertRaises(ValidationError):
                self._category(name, consent_approval_hours=24, **values)

    def test_consent_is_refused_when_a_category_starts_to_post(self):
        category = self._category(
            "Becomes accounting", approval_type="general", consent_approval_hours=24
        )
        with self.assertRaises(ValidationError):
            category.approval_type = "accounting"
        with self.assertRaises(ValidationError):
            self._category("Posting later", approval_type="accounting").write(
                {"consent_approval_hours": 1}
            )

    def test_the_cron_approves_no_payment_by_silence(self):
        paying = self._category("Silent payment", approval_type="payment")
        general = self._category(
            "Silent errand", approval_type="general", consent_approval_hours=1
        )
        self._set_consent_behind_the_form(paying, 1)
        held = self._pending_request(paying)
        control = self._pending_request(general)

        self.env["approval.request"].cron_consent_approval()

        self.assertEqual(control.state, "approved", "the cron did run")
        self.assertEqual(held.state, "pending")

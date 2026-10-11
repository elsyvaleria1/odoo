import re
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestCreditPostingBatch(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        grade = cls.env["credit.grade"].sudo().create({"name": "Batch posting grade"})
        cls.partners = cls.env["res.partner"].create(
            [{"name": f"Batch credit partner {index}"} for index in range(6)]
        )
        for partner in cls.partners:
            partner.sudo().with_company(cls.env.company).write(
                {"credit_grade_id": grade.id, "credit_trusted_amount": 1_000_000.0}
            )

    def _invoice(self, partner, amount):
        return self.init_invoice(
            "out_invoice", partner=partner, invoice_date="2026-01-15", amounts=[amount]
        )

    def test_posting_reads_the_credit_exposure_once_per_batch(self):
        invoices = self.env["account.move"].concat(
            *(self._invoice(partner, 100.0) for partner in self.partners)
        )

        def exposure_reads(moves):
            with self.capturedQueries() as queries:
                moves._check_posting_advisories()
            return {
                pattern: sum(1 for query in queries if re.search(pattern, query))
                for pattern in (
                    r'FROM "credit_profile"',
                    r'SUM\("account_move"\."amount_total_signed"\)',
                    r'FROM "credit_policy_rule"',
                )
            }

        exposure_reads(invoices[4:])
        self.assertEqual(exposure_reads(invoices[:2]), exposure_reads(invoices[:4]))

    def test_each_move_sees_the_other_drafts_it_saw_when_checked_alone(self):
        partner, other = self.partners[:2]
        outside = self._invoice(partner, 50.0)
        batch = (
            self._invoice(partner, 100.0)
            | self._invoice(partner, 200.0)
            | self._invoice(other, 300.0)
            | self._invoice(partner, 400.0)
        )
        Profile = type(self.env["credit.profile"])
        seen = []
        original = Profile._facts

        def recording(profile, kind, amount, immediate, term_days):
            facts = original(profile, kind, amount, immediate, term_days)
            seen.append((profile.partner_id, amount, facts["exposure"]))
            return facts

        with patch.object(Profile, "_facts", recording):
            batch._check_posting_advisories()

        drafts = outside | batch
        self.assertEqual(
            seen,
            [
                (
                    move.partner_id,
                    move.amount_total_signed,
                    sum(
                        draft.amount_total_signed
                        for draft in drafts - move
                        if draft.partner_id == move.partner_id
                    ),
                )
                for move in batch
            ],
        )

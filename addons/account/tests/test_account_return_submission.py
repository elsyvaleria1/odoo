from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon

MANUAL = (
    "odoo.addons.account.models.account_return_filing_manual.AccountReturnFilingManual"
)


@tagged("post_install", "-at_install")
class TestAccountReturnSubmission(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data["company"].write(
            {
                "vat": "US12345671",
                "phone_ids": [
                    Command.create({"number": "123456789", "type": "landline"})
                ],
                "email": "test@gmail.com",
            }
        )
        cls.return_type = cls.env["account.return.type"].create(
            {
                "category": "account_return",
                "default_deadline_periodicity": "monthly",
                "default_deadline_start_date": "2024-01-01",
                "name": "Filed VAT",
                "report_id": cls.env.ref("account.generic_tax_report").id,
                "states_workflow": "generic_state_review_submit",
                "filing_channel": "manual",
            }
        )

    def setUp(self):
        super().setUp()
        self.defers = []
        patcher = patch.object(
            type(self.env["ir.job"]),
            "_defer",
            lambda _self, seconds, reason="": self.defers.append((seconds, reason)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _reviewed_return(self):
        tax_return = self.return_type.with_context(
            forced_date_from=fields.Date.from_string("2024-02-01"),
            forced_date_to=fields.Date.from_string("2024-02-29"),
        )._try_create_returns_for_fiscal_year(self.env.company, False)
        with patch.object(
            self.registry["account.return"],
            "_generate_locking_attachments",
            lambda self, options: None,
        ):
            tax_return.action_validate()
        self.assertEqual(tax_return.state, "reviewed")
        return tax_return

    def _accepted_submission(self):
        tax_return = self._reviewed_return()
        action = tax_return.action_submit()
        submission = self.env[action["res_model"]].browse(action["res_id"])
        submission.external_ref = "ACK-2024-02"
        submission.action_send()
        return tax_return, submission

    # ------------------------------------------------------------------
    # The manual channel: the user filed outside Odoo and records it
    # ------------------------------------------------------------------

    def test_submitting_opens_a_draft_submission_without_submitting_yet(self):
        tax_return = self._reviewed_return()

        action = tax_return.action_submit()

        self.assertEqual(action["res_model"], "account.return.submission")
        submission = tax_return.submission_ids
        self.assertRecordValues(submission, [{"state": "draft", "channel": "manual"}])
        self.assertEqual(tax_return.state, "reviewed")

    def test_a_manual_filing_needs_evidence(self):
        tax_return = self._reviewed_return()
        tax_return.action_submit()

        with self.assertRaises(UserError):
            tax_return.submission_ids.action_send()
        self.assertEqual(tax_return.state, "reviewed")

    def test_recording_the_authority_reference_submits_the_return(self):
        tax_return, submission = self._accepted_submission()

        self.assertEqual(submission.state, "accepted")
        self.assertTrue(submission.date_accepted)
        self.assertEqual(tax_return.state, "submitted")
        self.assertTrue(tax_return.is_completed)

    def test_an_accepted_submission_cannot_change(self):
        _tax_return, submission = self._accepted_submission()

        with self.assertRaises(UserError):
            submission.external_ref = "something else"
        with self.assertRaises(UserError):
            self.env["account.return.submission.line"].create(
                {"submission_id": submission.id, "name": "late", "amount": 1.0}
            )
        with self.assertRaises(UserError):
            submission.unlink()

        receipt = self.env["ir.attachment"].create(
            {"name": "acuse.pdf", "raw": b"%PDF"}
        )
        submission.receipt_attachment_ids = [Command.link(receipt.id)]
        self.assertEqual(submission.receipt_attachment_ids, receipt)

    def test_a_filed_return_cannot_be_reset(self):
        tax_return, submission = self._accepted_submission()

        with self.assertRaises(UserError):
            tax_return.action_reset_tax_return_common()
        with self.assertRaises(UserError):
            tax_return.action_reset_2_states()
        self.assertEqual(submission.state, "accepted")

    def test_a_rejected_filing_allows_a_reset_and_stays_on_record(self):
        tax_return = self._reviewed_return()
        tax_return.action_submit()
        submission = tax_return.submission_ids
        submission._update_from_channel(
            "rejected",
            error_payload={"errors": [{"code": "E12", "message": "Bad period"}]},
        )

        tax_return.action_reset_2_states()

        self.assertEqual(tax_return.state, "new")
        self.assertEqual(submission.exists(), submission)
        self.assertEqual(submission.error_message, "[E12] Bad period")

    # ------------------------------------------------------------------
    # The channel contract, against fakes shaped like the real channels
    # ------------------------------------------------------------------

    def _draft_submission(self):
        tax_return = self._reviewed_return()
        tax_return.action_submit()
        return tax_return, tax_return.submission_ids

    def test_a_synchronous_channel_submits_on_the_spot(self):
        """Belgian Intervat: the authority answers the request itself."""

        def send(_self, submission):
            submission._update_from_channel("accepted", external_ref="BE-1")

        tax_return, submission = self._draft_submission()
        with patch(f"{MANUAL}._send_submission", send):
            submission.action_send()

        self.assertEqual(submission.state, "accepted")
        self.assertEqual(tax_return.state, "submitted")

    def test_an_acknowledging_channel_submits_once_a_poll_says_accepted(self):
        """Dutch SBR, UK GovTalk: acknowledge now, decide later."""
        answers = iter(["acknowledged", "accepted"])

        def send(_self, submission):
            submission._update_from_channel("acknowledged", external_ref="kenmerk-7")

        def poll(_self, submission):
            submission._update_from_channel(next(answers))

        tax_return, submission = self._draft_submission()
        with (
            patch(f"{MANUAL}._send_submission", send),
            patch(f"{MANUAL}._update_submission_status", poll),
        ):
            submission.action_send()
            jobs = (
                self.env["ir.job"]
                .sudo()
                .search(
                    [
                        (
                            "identity_key",
                            "=",
                            f"account.return.submission.{submission.id}.status",
                        )
                    ]
                )
            )
            self.assertEqual(len(jobs), 1)
            self.assertEqual(tax_return.state, "reviewed")

            submission._job_update_status()
            self.assertEqual(submission.state, "acknowledged")
            self.assertEqual(len(self.defers), 1)
            self.assertEqual(tax_return.state, "reviewed")

            submission._job_update_status()

        self.assertEqual(submission.state, "accepted")
        self.assertEqual(submission.external_ref, "kenmerk-7")
        self.assertEqual(tax_return.state, "submitted")
        self.assertEqual(len(self.defers), 1)

    def test_a_rejecting_poll_leaves_the_return_where_it_was(self):
        def send(_self, submission):
            submission._update_from_channel("acknowledged")

        def poll(_self, submission):
            submission._update_from_channel(
                "rejected", error_payload={"message": "Signature invalid"}
            )

        tax_return, submission = self._draft_submission()
        with (
            patch(f"{MANUAL}._send_submission", send),
            patch(f"{MANUAL}._update_submission_status", poll),
        ):
            submission.action_send()
            submission._job_update_status()

        self.assertEqual(submission.state, "rejected")
        self.assertEqual(submission.error_message, "Signature invalid")
        self.assertEqual(tax_return.state, "reviewed")

    def test_a_channel_needing_a_login_hands_back_an_action_and_resumes(self):
        """UK MTD, Belgian OAuth: the user logs in at the authority first."""
        logged_in = []
        login_action = {"type": "ir.actions.act_url", "url": "https://authority/login"}

        def send(_self, submission):
            if not logged_in:
                submission._update_from_channel("sending")
                return login_action
            submission._update_from_channel("accepted", external_ref="MTD-1")
            return None

        tax_return, submission = self._draft_submission()
        with patch(f"{MANUAL}._send_submission", send):
            self.assertEqual(submission.action_send(), login_action)
            self.assertEqual(tax_return.state, "reviewed")
            logged_in.append(True)
            self.assertIsNone(submission.action_send())

        self.assertEqual(submission.state, "accepted")
        self.assertEqual(tax_return.state, "submitted")

    def test_an_informative_return_posts_no_closing_and_locks_nothing(self):
        informative_type = self.env["account.return.type"].create(
            {
                "category": "account_return",
                "default_deadline_periodicity": "monthly",
                "default_deadline_start_date": "2024-01-01",
                "name": "Third-party operations",
                "report_id": self.env.ref("account.generic_tax_report").id,
                "is_informative": True,
            }
        )
        self.assertFalse(informative_type.is_tax_return_type)
        self.assertEqual(informative_type.states_workflow, "generic_state_review")
        lock_date = self.env.company.account_config_id.tax_lock_date
        tax_return = informative_type.with_context(
            forced_date_from=fields.Date.from_string("2024-02-01"),
            forced_date_to=fields.Date.from_string("2024-02-29"),
        )._try_create_returns_for_fiscal_year(self.env.company, False)

        with patch.object(
            self.registry["account.return"],
            "_generate_locking_attachments",
            lambda self, options: None,
        ):
            tax_return.action_validate()

        self.assertFalse(tax_return.closing_move_ids)
        self.assertEqual(self.env.company.account_config_id.tax_lock_date, lock_date)

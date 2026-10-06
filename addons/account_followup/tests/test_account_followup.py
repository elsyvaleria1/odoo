from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account_followup.models.followup_request import FollowupRequest
from odoo.addons.account_followup.tests.common import TestAccountFollowupCommon
from odoo.addons.mail.tests.common import MailCommon


@tagged("post_install", "-at_install")
class TestAccountFollowupReports(TestAccountFollowupCommon, MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["account_followup.followup.line"].search([]).unlink()

        pdf_render_patcher = patch.object(
            cls.env.registry["ir.actions.report"],
            "_render_html_to_pdf",
            lambda *args, **kwargs: b"0",
        )
        pdf_render_patcher.start()
        cls.addClassCleanup(pdf_render_patcher.stop)

    def create_followup(self, delay):
        return self.env["account_followup.followup.line"].create(
            {
                "name": f"followup {delay}",
                "delay": delay,
                "send_email": False,
                "company_id": self.company_data["company"].id,
            }
        )

    def create_invoice(self, date, partner=None):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": date,
                "invoice_date_due": date,
                "partner_id": partner.id if partner else self.partner_a.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "quantity": 1,
                            "price_unit": 500,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        return invoice

    def test_followup_responsible(self):
        """The followup responsible is resolved from partner, invoice user, and followup config."""
        self.first_followup_line = self.create_followup(delay=-10)

        user1 = self.env["res.users"].create(
            {
                "name": "A User",
                "login": "a_user",
                "email": "a@user.com",
                "group_ids": [(6, 0, [self.env.ref("account.group_account_user").id])],
            }
        )
        user2 = self.env["res.users"].create(
            {
                "name": "Another User",
                "login": "another_user",
                "email": "another@user.com",
                "group_ids": [(6, 0, [self.env.ref("account.group_account_user").id])],
            }
        )
        # 1- no info, use current user
        self.assertEqual(self.partner_a._get_followup_responsible(), self.env.user)

        # 2- set invoice user
        invoice1 = self.init_invoice(
            "out_invoice",
            partner=self.partner_a,
            invoice_date=fields.Date.from_string("2000-01-01"),
            amounts=[2000],
        )
        invoice2 = self.init_invoice(
            "out_invoice",
            partner=self.partner_a,
            invoice_date=fields.Date.from_string("2000-01-01"),
            amounts=[1000],
        )
        invoice1.invoice_user_id = user1
        invoice2.invoice_user_id = user2
        (invoice1 + invoice2).action_post()
        # Should pick invoice_user_id of the most delayed move, with highest residual amount in case of tie (invoice1)
        self.assertEqual(self.partner_a._get_followup_responsible(), user1)
        # If user1 is archived, it shouldn't be selected as responsible
        user1.active = False
        self.assertEqual(self.partner_a._get_followup_responsible(), self.env.user)
        user1.active = True

        self.partner_a.followup_line_id = self.first_followup_line

        # 3- A followup responsible user has been set on the partner
        self.partner_a.followup_responsible_id = user2
        self.assertEqual(self.partner_a._get_followup_responsible(), user2)

        # 4- Modify the default responsible on followup level
        self.partner_a.followup_line_id.activity_default_responsible_type = (
            "salesperson"
        )
        self.assertEqual(self.partner_a._get_followup_responsible(), user1)
        self.assertEqual(
            self.partner_a._get_followup_responsible(multiple_responsible=True),
            (user1 + user2),
        )

        self.partner_a.followup_line_id.activity_default_responsible_type = (
            "account_manager"
        )
        self.partner_a.user_id = user2
        self.assertEqual(
            self.partner_a._get_followup_responsible(), self.partner_a.user_id
        )

    def test_followup_activity(self):
        first_followup_line = self.create_followup(delay=10)
        first_followup_line.create_activity = True
        first_followup_line.activity_default_responsible_type = "salesperson"
        user1 = self.env["res.users"].create(
            {
                "name": "A User",
                "login": "a_user",
                "email": "a@user.com",
                "group_ids": [
                    Command.set([self.env.ref("account.group_account_user").id])
                ],
            }
        )
        user2 = self.env["res.users"].create(
            {
                "name": "Another User",
                "login": "another_user",
                "email": "another@user.com",
                "group_ids": [
                    Command.set([self.env.ref("account.group_account_user").id])
                ],
            }
        )
        inv1 = self.create_invoice("2022-01-02")
        inv1.invoice_user_id = user1
        inv2 = self.create_invoice("2022-01-02")
        inv2.invoice_user_id = user2

        with freeze_time("2022-01-13"):
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertEqual(self.partner_a.activity_ids.user_id, (user1 + user2))

    def test_followup_no_invoice_user_id(self):
        first_followup_line = self.create_followup(delay=10)
        first_followup_line.create_activity = True
        first_followup_line.activity_default_responsible_type = "salesperson"
        inv1 = self.create_invoice("2022-01-02")
        inv1.invoice_user_id = None
        with freeze_time("2022-01-13"):
            self.assertEqual(self.partner_a._get_followup_responsible(), self.user)

    def test_followup_line_and_status(self):
        self.first_followup_line = self.create_followup(delay=-10)
        self.second_followup_line = self.create_followup(delay=10)
        self.third_followup_line = self.create_followup(delay=15)

        self.create_invoice("2022-01-02")

        with freeze_time("2021-12-20"):
            # Today < due date + delay first followup level (negative delay -> reminder before due date)
            self.assertPartnerFollowup(
                self.partner_a, "no_action_needed", self.first_followup_line
            )

        with freeze_time("2021-12-24"):
            # Today = due date + delay first followup level
            self.assertPartnerFollowup(
                self.partner_a, "in_need_of_action", self.first_followup_line
            )

            # followup_next_action_date not exceeded but no invoice is overdue,
            # we should not be in status 'with_overdue_invoices' but 'no action needed'
            self.partner_a.followup_next_action_date = fields.Date.from_string(
                "2021-12-25"
            )
            self.assertPartnerFollowup(
                self.partner_a, "no_action_needed", self.first_followup_line
            )

        with freeze_time("2022-01-13"):
            # Today > due date + delay second followup level but first followup level not processed yet
            self.assertPartnerFollowup(
                self.partner_a, "in_need_of_action", self.first_followup_line
            )

            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            # Due date exceeded but first followup level processed
            # followup_next_action_date set in 20 days (delay 2nd level - delay 1st level = 10 - (-10) = 20)
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", self.second_followup_line
            )
            self.assertEqual(
                self.partner_a.followup_next_action_date,
                fields.Date.from_string("2022-02-02"),
            )

        with freeze_time("2022-02-03"):
            # followup_next_action_date exceeded and invoice not reconciled yet
            self.assertPartnerFollowup(
                self.partner_a, "in_need_of_action", self.second_followup_line
            )
            # execute second followup
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", self.third_followup_line
            )
            self.assertEqual(
                self.partner_a.followup_next_action_date,
                fields.Date.from_string("2022-02-08"),
            )

        with freeze_time("2022-02-09"):
            # followup_next_action_date exceeded and invoice not reconciled yet
            self.assertPartnerFollowup(
                self.partner_a, "in_need_of_action", self.third_followup_line
            )
            # execute third followup
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", self.third_followup_line
            )
            self.assertEqual(
                self.partner_a.followup_next_action_date,
                fields.Date.from_string("2022-02-14"),
            )

        with freeze_time("2022-02-15"):
            # followup_next_action_date exceeded and invoice not reconciled yet
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", self.third_followup_line
            )
            # executing the third followup again should do nothing as all the aml are linked to it
            followup_executed = self.partner_a._execute_followup(
                self.followup_request(self.partner_a)
            )
            self.assertFalse(followup_executed)

            # create a new overdue invoice
            self.create_invoice("2022-01-03")
            self.assertPartnerFollowup(
                self.partner_a, "in_need_of_action", self.third_followup_line
            )

            aml_ids = self.partner_a.unreconciled_aml_ids

            # Exclude every unreconciled invoice line.
            aml_ids.no_followup = True
            # Every unreconciled invoice line is excluded, so the result should be `no_action_needed`.
            self.assertPartnerFollowup(
                self.partner_a, "no_action_needed", self.third_followup_line
            )

            # It resets if we don't exclude them anymore.
            aml_ids.no_followup = False
            self.assertPartnerFollowup(
                self.partner_a, "in_need_of_action", self.third_followup_line
            )

            self.env["wizard.account.move.line.pay"].create(
                {
                    "line_ids": self.partner_a.unreconciled_aml_ids,
                }
            )._create_payments()
            self.assertPartnerFollowup(self.partner_a, None, None)

    def test_followup_multiple_invoices(self):
        followup_10 = self.create_followup(delay=10)
        followup_15 = self.create_followup(delay=15)
        followup_30 = self.create_followup(delay=30)

        self.create_invoice("2022-01-01")
        self.create_invoice("2022-01-02")

        # 9 days are not passed yet for the first followup level, current delay is 10-0=10
        with freeze_time("2022-01-10"):
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_10
            )

        # 10 days passed, current delay is 10-0=10, need to take action
        with freeze_time("2022-01-11"):
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_10)
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_15
            )

        # action taken 4 days ago, current delay is 15-10=5, nothing needed
        with freeze_time("2022-01-15"):
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_15
            )

        # action taken 5 days ago, current delay is 15-10=5, need to take action
        with freeze_time("2022-01-16"):
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_15)
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_30
            )

        # action taken 14 days ago, current delay is 30-15=15, nothing needed
        with freeze_time("2022-01-30"):
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_30
            )

        # action taken 15 days ago, current delay is 30-15=15, need to take action
        with freeze_time("2022-01-31"):
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_30)
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_30
            )

        # action taken 13 days ago, current delay is 15 (same on repeat), nothing needed
        with freeze_time("2022-02-14"):
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_30
            )

        # action taken 14 days ago, current delay is 15 (same on repeat), need to take action
        with freeze_time("2022-02-15"):
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_30)
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_30
            )

    def test_followup_multiple_invoices_with_first_payment(self):
        # Test the behavior of multiple invoices when the first one is paid
        followup_10 = self.create_followup(delay=10)
        followup_15 = self.create_followup(delay=15)

        invoice_01 = self.create_invoice("2022-01-01")
        self.create_invoice("2022-01-02")

        # 9 days are not passed yet for the first followup level, current delay is 10-0=10
        with freeze_time("2022-01-10"):
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_10
            )

        # 10 days passed, current delay is 10-0=10, need to take action
        with freeze_time("2022-01-11"):
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_10)
            # followup level for the second invoice shouldn't change since it's only 9 days overdue
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_15
            )

            self.env["wizard.account.move.line.pay"].create(
                {
                    "line_ids": invoice_01.line_ids.filtered(
                        lambda l: l.display_type == "payment_term"
                    ),
                }
            )._create_payments()

            # partner followup level goes back to 10 days after paying the first invoice
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_10
            )

        # action taken 4 days ago, current delay is 15-10=5, nothing needed
        with freeze_time("2022-01-15"):
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_10
            )

        # action taken 5 days ago, current delay is 15-10=5, need to take action
        with freeze_time("2022-01-16"):
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_10)
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_15
            )

    def test_followup_multiple_invoices_with_last_payment(self):
        # Test the behavior of multiple invoices when the last one is paid
        # Should behave exactly like test_followup_multiple_invoices_with_first_payment
        # because the followup is done at the same time.
        followup_10 = self.create_followup(delay=10)
        followup_15 = self.create_followup(delay=15)
        followup_30 = self.create_followup(delay=30)

        self.create_invoice("2022-01-01")
        invoice_02 = self.create_invoice("2022-01-02")

        # 9 days are not passed yet for the first followup level, current delay is 10-0=10
        with freeze_time("2022-01-10"):
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_10
            )

        # 10 days passed, current delay is 10-0=10, need to take action
        with freeze_time("2022-01-11"):
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_10)
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_15
            )

            self.env["wizard.account.move.line.pay"].create(
                {
                    "line_ids": invoice_02.line_ids.filtered(
                        lambda l: l.display_type == "payment_term"
                    ),
                }
            )._create_payments()

            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_15
            )

        # action taken 4 days ago, current delay is 15-10=5, nothing needed
        with freeze_time("2022-01-15"):
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_15
            )

        # action taken 5 days ago, current delay is 15-10=5, need to take action
        with freeze_time("2022-01-16"):
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_15)
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_30
            )

    def test_followup_status_entry_lines(self):
        """
        Creating an entry should not affect the followups as there is no concept of due date with this flow.
        """
        self.followup_line = self.create_followup(delay=10)

        with freeze_time("2022-01-02"):
            invoice = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "date": fields.Date.from_string("2022-01-02"),
                    "partner_id": self.partner_a.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line1",
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "debit": 500.0,
                                "credit": 0.0,
                            }
                        ),
                        Command.create(
                            {
                                "name": "counterpart line",
                                "account_id": self.company_data[
                                    "default_account_receivable"
                                ].id,
                                "debit": 0.0,
                                "credit": 500.0,
                            }
                        ),
                    ],
                }
            )
            invoice.action_post()

        with freeze_time("2022-01-13"):
            self.assertPartnerFollowup(
                self.partner_a, "no_action_needed", self.followup_line
            )

    def test_followup_status_residual(self):
        """
        Payments for partially paid invoices should contribute their residual to the due amount.
        This is required because the paid invoice's receivable line is reconciled, and thus is
        not considered in the query calculating followup_status.
        """

        self.followup_line = self.create_followup(delay=10)

        with freeze_time("2022-01-02"):
            invoice_1 = self.create_invoice("2022-01-02")
            self.create_invoice("2022-01-02")

            misc_payment_1 = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "date": fields.Date.from_string("2022-01-02"),
                    "partner_id": self.partner_a.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line1",
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "debit": 600.0,
                                "credit": 0.0,
                            }
                        ),
                        Command.create(
                            {
                                "name": "counterpart line",
                                "account_id": self.company_data[
                                    "default_account_receivable"
                                ].id,
                                "debit": 0.0,
                                "credit": 600.0,
                            }
                        ),
                    ],
                }
            )
            misc_payment_1.action_post()

            (invoice_1 + misc_payment_1).line_ids.filtered(
                lambda l: l.account_type == "asset_receivable"
            ).reconcile()

        with freeze_time("2022-01-13"):
            self.assertPartnerFollowup(
                self.partner_a, "in_need_of_action", self.followup_line
            )

    def test_followup_contact(self):
        billing_contact = self.env["res.partner"].browse(
            self.partner_a.address_get(["invoice"])["invoice"]
        )
        self.assertEqual(self.partner_a._get_followup_contact(), billing_contact)

    def test_followup_contact_is_singular(self):
        """`address_get` answers one id per type, so several billing children collapse."""
        for name in ("Billing One", "Billing Two"):
            self.env["res.partner"].create(
                {"name": name, "parent_id": self.partner_a.id, "type": "invoice"}
            )
        self.assertLessEqual(len(self.partner_a._get_followup_contact()), 1)

    def test_followup_cron(self):
        cron = self.env.ref("account_followup.ir_cron_follow_up")
        followup_10 = self.create_followup(delay=10)
        followup_10.auto_execute = True

        self.create_invoice("2022-01-01")

        # Check that no followup is automatically done if there is no action needed
        with (
            freeze_time("2022-01-10"),
            patch.object(self.env.registry["res.partner"], "_send_followup") as patched,
            self.sync_env_with_side_cursors(),
        ):
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_10
            )
            cron.method_direct_trigger()
            patched.assert_not_called()
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_10
            )

        # Check that the action is taken one and only one time when there is an action needed
        with (
            freeze_time("2022-01-11"),
            patch.object(self.env.registry["res.partner"], "_send_followup") as patched,
            self.sync_env_with_side_cursors(),
        ):
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_10)
            cron.method_direct_trigger()
            patched.assert_called_once()
            self.assertPartnerFollowup(
                self.partner_a, "with_overdue_invoices", followup_10
            )

    def test_onchange_residual_amount(self):
        """The SQL-computed residual amount on account move lines is correct after a partial payment."""
        invoice = self.create_invoice("2016-01-01")
        self.create_invoice("2016-01-02")

        self.env["wizard.account.move.line.pay"].with_context(
            active_ids=invoice.ids, active_model="account.move"
        ).create(
            {
                "payment_date": invoice.date,
                "amount": 100,
            }
        )._create_payments()

        self.assertRecordValues(self.partner_a, [{"total_due": 900.0}])
        self.assertRecordValues(
            self.partner_a.unreconciled_aml_ids.sorted(),
            [
                {"amount_residual_currency": 500.0},
                {"amount_residual_currency": 400.0},
            ],
        )

        self.assertRecordValues(
            self.partner_a.unreconciled_aml_ids.sorted(),
            [
                {"amount_residual_currency": 500.0},
                {"amount_residual_currency": 400.0},
            ],
        )

    def test_compute_total_due(self):
        self.create_invoice("2016-01-01")
        self.create_invoice("2017-01-01")
        self.create_invoice(fields.Date.today() + relativedelta(months=1))
        self.env["account.move"].create(
            [
                {
                    "move_type": "in_invoice",
                    "invoice_date": date,
                    "partner_id": self.partner_a.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "quantity": 1,
                                "price_unit": 500,
                                "tax_ids": [],
                            }
                        )
                    ],
                }
                for date in (
                    "2016-01-01",
                    "2017-01-01",
                    fields.Date.today() + relativedelta(months=1),
                )
            ]
        ).action_post()

        self.assertRecordValues(
            self.partner_a,
            [
                {
                    "total_due": 1500.0,
                    "total_overdue": 1000.0,
                    "total_net_due": 0.0,
                    "total_net_overdue": 0.0,
                }
            ],
        )

    def test_send_followup_no_due_date(self):
        """Send a followup report with an empty due date field."""
        self.create_followup(delay=0)
        self.create_invoice("2022-01-01")
        self.partner_a.unreconciled_aml_ids.write(
            {
                "date_maturity": False,
            }
        )

        self.partner_a._execute_followup(
            self.followup_request(self.partner_a, manual=True)
        )

    def test_followup_copy_data(self):
        """Duplicate a followup line, both a single record and several at once, with no defaults."""
        followup_50 = self.create_followup(delay=50)
        followup_60 = self.create_followup(delay=60)

        # Duplicate single record with no default values
        followup_50_duplicate = followup_50.copy()
        self.assertTrue(followup_50_duplicate)
        self.assertEqual(
            followup_50_duplicate.name, f"75 days (copy of {followup_50.name})"
        )

        # Duplicate multiple records at the same time with no default values
        multiple_followup_records = followup_50 + followup_60
        multiple_followup_records_duplicate = multiple_followup_records.copy()
        self.assertTrue(multiple_followup_records_duplicate)
        self.assertEqual(
            multiple_followup_records_duplicate[0].name,
            f"90 days (copy of {followup_50.name})",
        )
        self.assertEqual(
            multiple_followup_records_duplicate[1].name,
            f"105 days (copy of {followup_60.name})",
        )

    def test_manual_reminder_get_template_mail_addresses(self):
        """
        When opening wizard.res.partner.send.followup, the partner should always be in `email_recipient_ids`
        When adding a template, the template's partner_to, email_cc and email_to should be added to `email_recipient_ids` as well
        """
        mail_partner = self.env["res.partner"].create(
            {
                "name": "Mai Lang",
                "email": "mail.ang@test.com",
            }
        )
        mail_cc = self.env["res.partner"].create(
            {
                "name": "John Carmac",
                "email": "john.carmac@example.me",
            }
        )

        mail_template = self.env["mail.template"].create(
            {
                "name": "reminder",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "email_cc": mail_cc.email,
                "use_default_to": False,
            }
        )

        reminder = (
            self.env["wizard.res.partner.send.followup"]
            .with_context(
                active_model="res.partner",
                active_ids=mail_partner.ids,
            )
            .create({"template_id": mail_template.id})
        )

        self.assertTrue(
            mail_partner in reminder.email_recipient_ids,
            "Mai Lang should be in the Email Recipients List",
        )

        reminder.template_id = mail_template

        self.assertTrue(
            mail_cc in reminder.email_recipient_ids,
            "John Carmac should be in the Email Recipients list.",
        )
        self.assertTrue(
            mail_partner in reminder.email_recipient_ids,
            "Mai Lang should still be in the Email Recipients List",
        )

    def test_overdue_invoices_action_domain_includes_children_partners(self):
        """
        When checking overdue invoices for a company (partner), the action [action_view_overdue_entries] domain should also include
        the overdue invoices of its children partners.
        """

        # Step 1: Create contacts
        parent_contact = self.env["res.partner"].create(
            {
                "name": "Parent Contact",
                "is_company": True,
            }
        )
        child_contact = self.env["res.partner"].create(
            {
                "name": "Child Contact",
                "parent_id": parent_contact.id,
            }
        )

        # Step 2: Create an invoice for the child contact
        invoice_date = fields.Date.today() - relativedelta(months=1)
        invoice = self.create_invoice(invoice_date, child_contact)
        invoice.invoice_date_due = invoice_date

        # Step 3: Verify follow-up status and overdue invoices of the parent contact
        action = parent_contact.action_view_overdue_entries()
        overdue_invoices = self.env["account.move"].search(action["domain"])
        self.assertIn(invoice.id, overdue_invoices.ids)
        self.assertEqual(parent_contact.followup_status, "with_overdue_invoices")

    def test_journal_items_action_domain_filters_partner_posted_entries(self):
        """
        The action [action_view_partner_followup_journal_items] should return journal items
        belonging to the selected partner, only from posted moves, and limited
        to payable/receivable accounts marked as trade (non_trade = False).
        """
        test_partner = self.env["res.partner"].create(
            {
                "name": "Journal Items with Partner",
                "is_company": True,
                "customer_rank": 1,
            }
        )
        invoice_date = fields.Date.today() - relativedelta(months=1)

        # Create invoices
        normal_invoice = self.create_invoice(fields.Date.today(), test_partner)
        overdue_invoice = self.create_invoice(invoice_date, test_partner)

        action = test_partner.action_view_partner_followup_journal_items()

        # Validate context
        ctx = action["context"]
        self.assertEqual(ctx.get("search_default_partner_id"), [test_partner.id])
        self.assertEqual(ctx.get("search_default_posted"), 1)

        # Either receivable or payable should be set to 1
        self.assertEqual(ctx.get("search_default_trade_receivable"), 1)
        # Non-trade filters should be disabled
        self.assertEqual(ctx.get("search_default_non_trade_receivable"), 0)
        self.assertEqual(ctx.get("search_default_non_trade_payable", 0), 0)

        # Validate domain and results
        aml = self.env["account.move.line"].search(action["domain"])
        self.assertEqual(
            aml.ids, normal_invoice.line_ids.ids + overdue_invoice.line_ids.ids
        )

    def test_followup_template_recipients_with_cron(self):
        """
        A mail_cc defined on a template is honoured even when the followup is sent via
        `res.partner._send_followup_email` (the path used by the cron).
        Completes `test_manual_reminder_get_template_mail_addresses`.
        """
        self.partner_a.email = "test@test.com"
        mail_cc = self.env["res.partner"].create(
            {
                "name": "John Carmac",
                "email": "john.carmac@example.me",
            }
        )
        mail_template = self.env["mail.template"].create(
            {
                "name": "reminder",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "email_cc": mail_cc.email,
                "use_default_to": False,
            }
        )
        followup_10 = self.create_followup(delay=10)
        followup_10.mail_template_id = mail_template
        self.create_invoice("2025-05-01")

        with freeze_time("2025-05-12"), self.mock_mail_gateway(mail_unlink_sent=False):
            self.partner_a._send_followup_email(
                self.followup_request(self.partner_a, followup_line=followup_10)
            )
        self.assertMailMail(mail_cc, "sent", author=self.env.user.partner_id)

    def test_followup_attachments_template_without_attachment(self):
        """A mail template with no static attachment still yields a followup payload.

        `mail.template._prepare_attachment_vals` only seeds "attachment_ids" when the
        template actually carries one, so indexing it unconditionally raised KeyError
        for every template shipped in data/ -- the manual wizard, the "Process
        Follow-ups" action and the cron all died on it.
        """
        followup_10 = self.create_followup(delay=10)
        followup_10.mail_template_id = self.env["mail.template"].create(
            {
                "name": "bare",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
            }
        )
        self.assertFalse(followup_10.mail_template_id.attachment_ids)
        self.create_invoice("2016-01-01")

        request = self.partner_a._attach_followup_documents(
            self.followup_request(self.partner_a, followup_line=followup_10)
        )
        self.assertEqual(
            list(request.attachment_ids),
            [self.env["ir.attachment"].search([], limit=1, order="id desc").id],
        )

    def _make_branch(self, name="Branch"):
        branch = self.env["res.company"].create(
            {"name": name, "parent_id": self.env.company.id}
        )
        self.env.user.company_ids |= branch
        self.cr.precommit.run()  # load the branch's chart of accounts
        return branch

    def _create_branch_invoice(self, branch, date, price_unit=500):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": date,
                "invoice_date_due": date,
                "date": date,
                "partner_id": self.partner_a.id,
                "company_id": branch.id,
                "invoice_line_ids": [
                    Command.create({"quantity": 1, "price_unit": price_unit})
                ],
            }
        )
        invoice.action_post()
        return invoice

    def test_followup_levels_are_inherited_by_branches(self):
        """A branch is followed up with the levels its parent company defines.

        The Python lookups resolved levels `parent_of` the active company while the
        SQL joined them with `=`, so a branch saw its overdue amount but no level and
        never left 'with_overdue_invoices'.
        """
        branch = self._make_branch()
        followup_10 = self.create_followup(delay=10)  # on the parent company
        self._create_branch_invoice(branch, "2016-01-01")

        with freeze_time("2016-01-20"):
            partner = self.partner_a.with_context(allowed_company_ids=[branch.id])
            partner.invalidate_recordset(["followup_status", "followup_line_id"])
            self.assertEqual(partner.total_overdue, 500.0)
            self.assertEqual(partner.followup_status, "in_need_of_action")
            self.assertEqual(partner.followup_line_id, followup_10)

    def test_followup_next_date_uses_inherited_levels(self):
        """The gap to the next reminder is read from the levels the company inherits."""
        branch = self._make_branch()
        self.create_followup(delay=15)
        self.create_followup(delay=60)

        with freeze_time("2016-01-20"):
            branch_env = self.env["res.partner"].with_context(
                allowed_company_ids=[branch.id]
            )
            first = branch_env._get_first_followup_level()
            self.assertEqual(first.delay, 15)
            self.assertEqual(
                first.with_context(allowed_company_ids=[branch.id])._get_next_date(),
                fields.Date.to_date("2016-03-05"),
                "60 - 15 = 45 days, not this level's own 15",
            )

    def test_followup_failed_send_keeps_the_partner_due(self):
        """A send that raises must not advance the next-reminder date.

        The cron catches UserError per partner and carries on; advancing the date
        first pushed a customer that could not be reached past its own due date, so
        it silently dropped out of every following run.
        """
        self.create_followup(delay=10).write({"auto_execute": True, "send_email": True})
        self.partner_a.email = False
        self.partner_a.child_ids.email = False
        self.create_invoice("2016-01-01")

        level = self.env["account_followup.followup.line"].search([], limit=1)
        with freeze_time("2016-01-20"), self.sync_env_with_side_cursors():
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", level)
            self.env.ref("account_followup.ir_cron_follow_up").method_direct_trigger()
            self.assertFalse(
                self.partner_a.followup_next_action_date,
                "nothing was sent, so nothing is scheduled",
            )
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", level)

    def test_followup_status_is_not_cached_across_a_payment(self):
        """The follow-up status follows the data inside one transaction.

        A cursor-level cache used to answer 'in_need_of_action' for a partner whose
        invoice had just been paid in full, and both the cron and the test helper had
        to pop it by hand.
        """
        followup_10 = self.create_followup(delay=10)
        invoice = self.create_invoice("2016-01-01")

        with freeze_time("2016-01-20"):
            self.env["res.partner"].search(
                [("followup_status", "in", ["in_need_of_action"])]
            )
            self.env["wizard.account.move.line.pay"].with_context(
                active_ids=invoice.ids, active_model="account.move"
            ).create({"payment_date": "2016-01-20"})._create_payments()

            self.partner_a.invalidate_recordset(["followup_status", "followup_line_id"])
            self.assertEqual(self.partner_a.total_due, 0.0)
            self.assertEqual(self.partner_a.followup_status, "no_action_needed")
            self.assertFalse(self.partner_a.followup_line_id)
        self.assertTrue(followup_10)

    def test_unpaid_invoices_count_follows_new_invoices(self):
        """The unpaid-invoice count and has_moves invalidate when invoices change."""
        self.create_invoice("2016-01-01")
        self.assertEqual(self.partner_a.unpaid_invoices_count, 1)
        self.assertTrue(self.partner_a.has_moves)

        self.create_invoice("2016-02-01")
        self.assertEqual(self.partner_a.unpaid_invoices_count, 2)

    def test_followup_responsible_skips_archived_users(self):
        """An archived salesperson must not ride along on an active one.

        `activity_schedule` accepts an inactive user without complaining, so the
        activity lands where nobody will ever see it.
        """
        level = self.create_followup(delay=0)
        level.write(
            {
                "create_activity": True,
                "activity_default_responsible_type": "salesperson",
                "activity_type_id": self.env.ref("mail.mail_activity_data_call").id,
                "activity_summary": "chase",
            }
        )
        users = self.env["res.users"].create(
            [
                {"name": "Archived One", "login": "arch_one", "email": "a1@x.com"},
                {"name": "Active One", "login": "act_one", "email": "a2@x.com"},
            ]
        )
        archived, active = users
        for user, amount in zip(users, (2000, 1000), strict=True):
            invoice = self.init_invoice(
                "out_invoice",
                partner=self.partner_a,
                invoice_date=fields.Date.from_string("2020-01-01"),
                amounts=[amount],
            )
            invoice.invoice_user_id = user
            invoice.action_post()
        self.partner_a.invalidate_recordset()
        self.assertEqual(
            self.partner_a._get_followup_responsible(multiple_responsible=True),
            archived + active,
        )

        archived.active = False
        self.partner_a.invalidate_recordset()
        self.assertEqual(
            self.partner_a._get_followup_responsible(multiple_responsible=True),
            active,
            "the archived salesperson must be dropped, not carried by the active one",
        )

        self.partner_a._execute_followup(self.followup_request(self.partner_a))
        activities = self.env["mail.activity"].search(
            [("res_model", "=", "res.partner"), ("res_id", "=", self.partner_a.id)]
        )
        self.assertEqual(activities.user_id, active)

    def test_followup_responsible_account_manager_skips_archived_user(self):
        """An archived account manager must not be handed back unfiltered.

        The `account_manager` branch used to return `self.user_id` before the
        active-user filter the rest of the method enforces, so an archived
        salesperson kept coming back as the followup responsible.
        """
        self.first_followup_line = self.create_followup(delay=-10)
        self.partner_a.followup_line_id = self.first_followup_line
        self.partner_a.followup_line_id.activity_default_responsible_type = (
            "account_manager"
        )
        user = self.env["res.users"].create(
            {"name": "Manager One", "login": "manager_one", "email": "m1@x.com"}
        )
        self.partner_a.user_id = user
        self.assertEqual(self.partner_a._get_followup_responsible(), user)

        user.active = False
        self.partner_a.invalidate_recordset()
        self.assertEqual(
            self.partner_a._get_followup_responsible(),
            self.env.user,
            "the archived account manager must be dropped, not returned unfiltered",
        )

    def test_statusbar_level_change_moves_the_reminder_date(self):
        """Clicking the statusbar must not publish the next level as due now.

        The status query gates on the level the lines already carry; only
        followup_next_action_date holds the next one back.
        """
        first = self.create_followup(delay=15)
        second = self.create_followup(delay=30)
        self.create_invoice("2020-01-01")

        with freeze_time("2020-01-16"):
            self.partner_a.invalidate_recordset()
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", first)
            self.partner_a.followup_line_id = second

        with freeze_time("2020-01-17"):
            self.partner_a.invalidate_recordset()
            self.assertEqual(
                self.partner_a.followup_next_action_date,
                fields.Date.from_string("2020-01-31"),
                "the second level is due 30 days after the due date, not at once",
            )
            self.assertPartnerFollowup(self.partner_a, "with_overdue_invoices", second)

        with freeze_time("2020-01-31"):
            self.partner_a.invalidate_recordset()
            self.assertPartnerFollowup(self.partner_a, "in_need_of_action", second)

    def test_followup_level_tie_between_a_branch_and_its_parent(self):
        """`unique(company_id, delay)` is per company, so a chain can tie on delay.

        The branch's own level wins, and the SQL and `_search_applicable` must say so
        together -- they used to answer with different records.
        """
        branch = self._make_branch("Tie Branch")
        parent_level = self.create_followup(delay=15)
        branch_level = self.env["account_followup.followup.line"].create(
            {
                "name": "branch 15",
                "delay": 15,
                "send_email": False,
                "company_id": branch.id,
            }
        )
        self._create_branch_invoice(branch, "2020-01-01")

        branch_partner = self.partner_a.with_company(branch).with_context(
            allowed_company_ids=branch.ids
        )
        rows = branch_partner._query_followup_data([self.partner_a.id])
        self.assertEqual(
            rows[self.partner_a.id]["followup_line_id"],
            branch_level.id,
            "the branch's own level must win over the one it inherits",
        )
        self.assertEqual(
            branch_partner._get_first_followup_level(),
            branch_level,
            "_search_applicable must break the tie the same way the SQL does",
        )
        branch_partner._update_next_followup_action_date(branch_level)
        self.assertEqual(
            branch_partner.unreconciled_aml_ids.followup_line_id,
            branch_level,
            "and so must the level stamped on the journal items -- three answers, "
            "one question",
        )
        self.assertNotEqual(parent_level, branch_level)

    def test_search_by_followup_line_can_ask_for_no_level(self):
        """`= False` asks about the absence of a level; it used to match nothing.

        A partner sitting in the follow-up data with a NULL level is an ordinary
        parent+branch state: the branch's own level is out of scope once you act
        for the parent, so the LATERAL that picks it finds nothing.
        """
        branch = self._make_branch("Levelless Branch")
        parent_level = self.create_followup(delay=0)
        branch_level = self.env["account_followup.followup.line"].create(
            {
                "name": "branch 15",
                "delay": 15,
                "send_email": False,
                "company_id": branch.id,
            }
        )
        stamped = self._create_branch_invoice(branch, "2020-01-01")
        self._create_branch_invoice(branch, "2020-01-02")
        stamped.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        ).followup_line_id = branch_level

        Partner = self.env["res.partner"].with_context(
            allowed_company_ids=[self.env.company.id, branch.id]
        )
        levelless = self.partner_a.with_env(Partner.env)
        levelless.invalidate_recordset()
        self.assertEqual(levelless.followup_status, "in_need_of_action")
        self.assertFalse(levelless.followup_line_id, "the premise: no level of its own")

        self.assertIn(
            levelless,
            Partner.search([("followup_line_id", "=", False)]),
            "'= False' must find the partner whose followup_line_id is False",
        )
        self.assertNotIn(
            levelless,
            Partner.search([("followup_line_id", "!=", False)]),
            "'!= False' asks for the partners that do carry a level",
        )
        # And the level-valued half still answers as before.
        self.assertNotIn(
            levelless, Partner.search([("followup_line_id", "=", parent_level.id)])
        )
        self.assertIn(
            levelless, Partner.search([("followup_line_id", "!=", parent_level.id)])
        )

    def test_missing_info_judges_the_level_the_send_will_use(self):
        """The pre-check and the send must resolve the same level.

        When the customer carries none of its own -- an ordinary parent+branch
        state -- `FollowupRequest.prepare` falls back to the first level while the
        pre-check read an empty recordset, found nothing missing, and handed the
        customer to a send that then raised.
        """
        branch = self._make_branch("Precheck Branch")
        first = self.create_followup(delay=0)
        first.write({"send_email": True})
        branch_level = self.env["account_followup.followup.line"].create(
            {
                "name": "branch 15",
                "delay": 15,
                "send_email": True,
                "company_id": branch.id,
            }
        )
        self.partner_a.write({"email": False, "child_ids": [Command.clear()]})
        stamped = self._create_branch_invoice(branch, "2020-01-01")
        self._create_branch_invoice(branch, "2020-01-02")
        stamped.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        ).followup_line_id = branch_level

        partner = self.partner_a.with_context(
            allowed_company_ids=[self.env.company.id, branch.id]
        )
        partner.invalidate_recordset()
        self.assertEqual(partner.followup_status, "in_need_of_action")
        self.assertFalse(partner.followup_line_id, "the premise: no level of its own")
        self.assertEqual(
            FollowupRequest.prepare(partner).followup_line,
            first,
            "the send falls back to the first level",
        )
        self.assertTrue(
            partner._has_missing_followup_info(),
            "so the pre-check must judge that level, not the empty one",
        )

    def test_manual_reminder_wizard_without_a_customer_says_so(self):
        """The action is reachable without an active record; say what is wrong."""
        Wizard = self.env["wizard.res.partner.send.followup"]
        with self.assertRaises(UserError):
            Wizard.default_get(["partner_id"])
        other = self.env["res.partner"].create({"name": "Second"})
        with self.assertRaises(UserError):
            Wizard.with_context(
                active_model="res.partner",
                active_ids=(self.partner_a + other).ids,
            ).default_get(["partner_id"])
        # and the way the partner form opens it still works
        defaults = Wizard.with_context(
            active_model="res.partner", active_ids=self.partner_a.ids
        ).default_get(["partner_id"])
        self.assertEqual(defaults["partner_id"], self.partner_a.id)

    def test_no_statement_is_rendered_when_nothing_is_sent(self):
        """A level that goes out on no channel must not pay for a report export."""
        level = self.create_followup(delay=0)
        level.write({"send_email": False, "send_sms": False, "auto_execute": True})
        self.create_invoice("2020-01-01")
        self.partner_a.invalidate_recordset()

        def attachments():
            return self.env["ir.attachment"].search_count(
                [("res_model", "=", "res.partner"), ("res_id", "=", self.partner_a.id)]
            )

        before = attachments()
        self.assertTrue(
            self.partner_a._execute_followup(self.followup_request(self.partner_a))
        )
        self.assertEqual(
            attachments(), before, "no channel wanted a document, so none was built"
        )

    def test_request_alone_does_not_bypass_the_due_check(self):
        """Forcing a channel must not also force a send that is not due."""
        self.create_followup(delay=30)
        self.create_invoice("2020-01-01")

        with freeze_time("2020-01-05"):
            self.partner_a.invalidate_recordset()
            self.assertNotEqual(self.partner_a.followup_status, "in_need_of_action")
            self.assertFalse(
                self.partner_a._execute_followup(self.followup_request(self.partner_a)),
                "a non-manual request is due only while the status says so",
            )
            self.assertTrue(
                self.partner_a._execute_followup(
                    self.followup_request(self.partner_a, manual=True)
                ),
                "a manual reminder is due because a user asked for it",
            )

    def test_search_followup_line_matches_partners_without_a_level(self):
        """A partner carrying no level satisfies a negative operator."""
        other_company = self.env["res.company"].create({"name": "Unrelated Co"})
        foreign_level = self.env["account_followup.followup.line"].create(
            {
                "name": "foreign",
                "delay": 10,
                "send_email": False,
                "company_id": other_company.id,
            }
        )
        self.create_invoice("2020-01-01")
        self.partner_a.invalidate_recordset()
        self.assertFalse(
            self.partner_a.followup_line_id, "no level of ours applies to this partner"
        )
        self.assertIn(
            self.partner_a,
            self.env["res.partner"].search(
                [("followup_line_id", "!=", foreign_level.id)]
            ),
        )

    def test_missing_information_wizard_carries_its_partners(self):
        """The wizard holds the partners in a field, not in a bare context key."""
        level = self.create_followup(delay=0)
        level.send_email = True
        self.partner_a.email = False
        self.create_invoice("2020-01-01")
        self.partner_a.invalidate_recordset()

        action = self.partner_a.action_manually_process_automatic_followups()
        self.assertEqual(
            action["res_model"], "wizard.res.partner.view.followup.missing.info"
        )
        wizard = (
            self.env["wizard.res.partner.view.followup.missing.info"]
            .with_context(**action["context"])
            .create({})
        )
        self.assertEqual(wizard.partner_ids, self.partner_a)
        self.assertEqual(
            wizard.view_partners_action()["domain"],
            [("id", "in", self.partner_a.ids)],
        )

    def test_has_moves_scopes_like_the_total_it_gates(self):
        """The stat button must not appear reading nothing.

        `has_moves` shows it and `total_net_due` fills it; counting them over
        different company sets rendered an empty button.
        """
        other = self.env["res.company"].create({"name": "Other Co"})
        self.env["account.chart.template"].try_loading(
            "generic_coa", company=other, install_demo=False
        )
        self.env.user.company_ids |= other
        self.cr.precommit.run()
        journal = self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", other.id)], limit=1
        )
        self.env["account.move"].with_company(other).create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2020-01-01",
                "invoice_date_due": "2020-01-01",
                "partner_id": self.partner_a.id,
                "journal_id": journal.id,
                "invoice_line_ids": [
                    Command.create({"quantity": 1, "price_unit": 500, "tax_ids": []})
                ],
            }
        ).action_post()

        seen_from_main = self.partner_a.with_company(self.env.company).with_context(
            allowed_company_ids=(self.env.company | other).ids
        )
        seen_from_main.invalidate_recordset()
        self.assertFalse(
            seen_from_main.has_moves,
            "nothing is due in the active company, so the button must stay hidden",
        )
        self.assertEqual(seen_from_main.total_net_due, 0.0)

        seen_from_other = self.partner_a.with_company(other).with_context(
            allowed_company_ids=other.ids
        )
        seen_from_other.invalidate_recordset()
        self.assertTrue(seen_from_other.has_moves)
        self.assertEqual(seen_from_other.total_net_due, 500.0)

    def test_followup_searches_compose_with_the_rest_of_the_domain(self):
        """The search returns a subquery, so a narrower domain still narrows it."""
        level = self.create_followup(delay=0)
        self.create_invoice("2020-01-01")
        other_partner = self.env["res.partner"].create({"name": "Untouched"})
        self.create_invoice("2020-01-01", partner=other_partner)
        self.partner_a.invalidate_recordset()

        Partner = self.env["res.partner"]
        # The property that makes it composable: a subquery PostgreSQL can push the
        # rest of the domain into, not one id per matching partner in the database.
        for domain in (
            Partner._search_status("in", ["in_need_of_action"]),
            Partner._search_followup_line("in", [level.id]),
        ):
            self.assertNotIsInstance(
                domain[0][2], list, "the search must hand back a subquery"
            )

        both = Partner.search([("followup_line_id", "=", level.id)])
        self.assertIn(self.partner_a, both)
        self.assertIn(other_partner, both)

        narrowed = Partner.search(
            [("followup_line_id", "=", level.id), ("id", "=", self.partner_a.id)]
        )
        self.assertEqual(narrowed, self.partner_a)
        self.assertEqual(
            Partner.search_count(
                [
                    ("followup_status", "=", "in_need_of_action"),
                    ("id", "=", other_partner.id),
                ]
            ),
            1,
        )

    def test_sms_reaches_the_billing_contact(self):
        """Logged on the customer, addressed to the contact -- as the email path does."""
        level = self.create_followup(delay=0)
        level.write({"send_email": False, "send_sms": True})
        self.partner_a.write(
            {
                "is_company": True,
                "phone_ids": [
                    Command.create({"number": "+32470000000", "type": "landline"})
                ],
            }
        )
        billing = self.env["res.partner"].create(
            {
                "name": "Billing Contact",
                "parent_id": self.partner_a.id,
                "type": "invoice",
                "phone_ids": [
                    Command.create({"number": "+32471111111", "type": "landline"})
                ],
            }
        )
        self.create_invoice("2020-01-01")
        self.partner_a.invalidate_recordset()
        self.assertEqual(self.partner_a._get_followup_contact(), billing)

        self.partner_a._execute_followup(self.followup_request(self.partner_a))
        sms = self.env["sms.sms"].search([], order="id desc", limit=1)
        self.assertEqual(
            sms.number,
            billing._phone_get_number().number,
            "the contact's number is dialled",
        )
        self.assertEqual(sms.partner_id, billing, "and the contact is the recipient")

    def test_cron_logs_and_retriggers_when_it_truncates(self):
        """The overflow must not wait a day in silence."""
        level = self.create_followup(delay=0)
        level.write({"send_email": False, "send_sms": False, "auto_execute": True})
        partners = self.env["res.partner"].create(
            [{"name": f"Batch {i}"} for i in range(3)]
        )
        for partner in partners:
            self.create_invoice("2020-01-01", partner=partner)
        partners.invalidate_recordset()

        cron = self.env.ref("account_followup.ir_cron_follow_up")
        triggers = self.env["ir.cron.trigger"].search_count([("cron_id", "=", cron.id)])
        self.patch(self.env.registry["res.partner"], "FOLLOWUP_CRON_BATCH_SIZE", 2)
        with self.assertLogs(
            "odoo.addons.account_followup.models.res_partner", "INFO"
        ) as capture:
            # as the cron itself runs: it sweeps every company in the database
            self.env["res.partner"].sudo()._cron_execute_followup()
        self.assertTrue(
            any("sending 2 this pass" in line for line in capture.output),
            f"the truncation must be logged, got {capture.output}",
        )
        self.assertGreater(
            self.env["ir.cron.trigger"].search_count([("cron_id", "=", cron.id)]),
            triggers,
            "the cron must re-trigger itself for the partners it did not reach",
        )

    def test_computes_agree_on_a_record_held_as_new(self):
        """A dirty form holds the customer as a NewId; the figures must not zero."""
        self.create_followup(delay=0)
        self.create_invoice("2020-01-01")
        saved = self.partner_a
        saved.invalidate_recordset()
        expected = {
            "has_moves": saved.has_moves,
            "total_net_due": saved.total_net_due,
            "total_due": saved.total_due,
            "unpaid_invoices_count": saved.unpaid_invoices_count,
            "unreconciled_aml_ids": len(saved.unreconciled_aml_ids),
            "followup_status": saved.followup_status,
        }
        self.assertEqual(
            expected,
            {
                "has_moves": True,
                "total_net_due": 500.0,
                "total_due": 500.0,
                "unpaid_invoices_count": 1,
                "unreconciled_aml_ids": 1,
                "followup_status": "in_need_of_action",
            },
            "the saved record is the premise; the assertion below is the point",
        )

        # Exactly how the web client holds a record whose form is open:
        # web/models/web_onchange.py builds `self.new(cache_values, origin=self)`.
        dirty = self.env["res.partner"].new(origin=saved)
        self.assertEqual(
            {
                "has_moves": dirty.has_moves,
                "total_net_due": dirty.total_net_due,
                "total_due": dirty.total_due,
                "unpaid_invoices_count": dirty.unpaid_invoices_count,
                "unreconciled_aml_ids": len(dirty.unreconciled_aml_ids),
                "followup_status": dirty.followup_status,
            },
            expected,
            "a NewId record must read the same figures as the record it originates from",
        )

    def test_cron_skips_a_company_it_may_not_act_for(self):
        """One company the scheduler user cannot enter must not cost the rest."""
        foreign = self.env["res.company"].create({"name": "Foreign Co"})
        scheduler = self.env["res.users"].create(
            {
                "name": "Scheduler",
                "login": "followup_scheduler",
                "company_id": self.env.company.id,
                "company_ids": [Command.set(self.env.company.ids)],
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("base.group_erp_manager").id,
                            self.env.ref("account.group_account_manager").id,
                        ]
                    )
                ],
            }
        )
        # The premise, not an assumption: an ERP manager reads every company row
        # while belonging to one. That is the gap the cron used to fall into.
        self.assertIn(foreign, self.env["res.company"].with_user(scheduler).search([]))
        self.assertNotIn(foreign, scheduler.company_ids)

        with self.assertLogs(
            "odoo.addons.account_followup.models.res_partner", "WARNING"
        ) as capture:
            self.env["res.partner"].with_user(scheduler)._cron_execute_followup()
        self.assertTrue(
            any("Foreign Co" in line for line in capture.output),
            f"the skipped company must be named, got {capture.output}",
        )

    def test_cron_as_superuser_still_sweeps_every_company(self):
        """The su path is what runs today; narrowing it would be a silent change."""
        self.env["res.company"].create({"name": "Foreign Co"})
        every = self.env["res.company"].sudo().search([])
        entered = []
        Partner = self.env.registry["res.partner"]
        original = Partner._cron_execute_followup_company

        def spy(records):
            entered.append(records.env.context.get("allowed_company_ids"))
            return original(records)

        self.patch(Partner, "_cron_execute_followup_company", spy)
        self.env["res.partner"].sudo()._cron_execute_followup()
        self.assertEqual(
            [ids[0] for ids in entered],
            every.ids,
            "a superuser cron must still enter every company, in _order",
        )

    def test_cron_runs_the_status_query_once_per_pass(self):
        """The cron already holds every answer `_execute_followup` would re-query."""
        level = self.create_followup(delay=0)
        level.auto_execute = True
        due = self.partner_a | self.partner_b
        for partner in due:
            partner.followup_reminder_type = "automatic"
            self.create_invoice("2020-01-01", partner=partner)

        calls = []
        Partner = self.env.registry["res.partner"]
        original = Partner._query_followup_data

        def spy(records, all_partners=False):
            calls.append("all" if all_partners else "some")
            return original(records, all_partners=all_partners)

        self.patch(Partner, "_query_followup_data", spy)
        self.env["res.partner"]._cron_execute_followup_company()

        self.assertEqual(
            calls,
            ["all"],
            "one pass must execute the status query once; a second call means "
            "_execute_followup re-derived what the cron had already read",
        )
        self.assertEqual(
            due.unreconciled_aml_ids.followup_line_id,
            level,
            "and the pass must still have done the work",
        )

    def test_primed_status_matches_what_the_compute_would_answer(self):
        """Priming the cache must not become a second opinion."""
        level = self.create_followup(delay=0)
        self.create_invoice("2020-01-01")
        partner = self.partner_a

        partner.invalidate_recordset()
        computed = (partner.followup_status, partner.followup_line_id)

        partner.invalidate_recordset()
        partner._set_followup_status(partner._query_followup_data())
        self.assertEqual(
            (partner.followup_status, partner.followup_line_id),
            computed,
            "the primed answer must equal the computed one",
        )
        self.assertEqual(computed, ("in_need_of_action", level))

        # A dependency changing must still win over what was primed.
        partner.followup_next_action_date = fields.Date.today() + relativedelta(days=7)
        self.assertEqual(
            partner.followup_status,
            "with_overdue_invoices",
            "priming must not survive a write to a field the status depends on",
        )

    def test_missing_info_agrees_with_who_the_send_would_reach(self):
        """A template that names an address is an address; the customer is not skipped."""
        self.partner_a.write({"email": False, "child_ids": [Command.clear()]})
        known = self.env["res.partner"].create(
            {"name": "Known Billing", "email": "known@x.com"}
        )
        report = self.env["account.followup.report"]
        for label, template_vals in (
            ("partner_to", {"partner_to": str(known.id), "use_default_to": False}),
            ("email_to", {"email_to": "billing@x.com", "use_default_to": False}),
            ("email_cc", {"email_cc": "cc@x.com", "use_default_to": False}),
        ):
            with self.subTest(template=label):
                level = self.partner_a.followup_line_id or self.create_followup(delay=0)
                level.write(
                    {
                        "send_email": True,
                        "mail_template_id": self.env["mail.template"]
                        .create(
                            {
                                "name": label,
                                "model_id": self.env["ir.model"]._get_id("res.partner"),
                                "subject": "s",
                                "body_html": "<p>b</p>",
                                **template_vals,
                            }
                        )
                        .id,
                    }
                )
                self.create_invoice("2020-01-01")
                self.partner_a.invalidate_recordset()
                request = self.followup_request(self.partner_a)
                reachable = report._get_email_recipients(request).filtered(
                    lambda contact: contact.email and contact.email.strip()
                )
                self.assertTrue(reachable, "the template supplies an address")
                self.assertFalse(
                    self.partner_a._has_missing_followup_info(),
                    "the customer is reachable, so it must not be skipped",
                )

    def test_missing_info_still_flags_a_customer_nobody_can_reach(self):
        level = self.create_followup(delay=0)
        level.write({"send_email": True, "mail_template_id": False})
        self.partner_a.write({"email": False, "child_ids": [Command.clear()]})
        self.create_invoice("2020-01-01")
        self.partner_a.invalidate_recordset()
        self.assertTrue(self.partner_a._has_missing_followup_info())

    def test_unreconciled_aml_ids_is_not_writable(self):
        """It is computed with no inverse; a write used to be silently discarded."""
        self.create_followup(delay=0)
        self.create_invoice("2020-01-01")
        self.partner_a.invalidate_recordset()
        self.assertTrue(self.partner_a.unreconciled_aml_ids)
        self.assertTrue(
            self.env["res.partner"]._fields["unreconciled_aml_ids"].readonly,
            "a computed field with no inverse must not advertise itself as writable",
        )

    def test_unreconciled_aml_ids_readable_without_journal_access(self):
        """A user who may read a partner but not its journal items sees no dues,
        not an AccessError. unreconciled_aml_ids carries no group (unlike the
        total_* fields), so its read still reaches _compute_total_due."""
        self.create_followup(delay=0)
        self.create_invoice("2020-01-01")
        plain_user = self.env["res.users"].create(
            {
                "name": "No Journal Access",
                "login": "no_journal_access_followup",
                "group_ids": [Command.set([self.env.ref("base.group_user").id])],
            }
        )
        self.assertFalse(
            self.env["account.move.line"].with_user(plain_user).has_access("read")
        )
        partner = self.partner_a.with_user(plain_user)
        partner.invalidate_recordset()
        # Must not raise; the statistic is empty for a user who cannot see the moves.
        self.assertFalse(partner.unreconciled_aml_ids)

    def test_followup_line_copy_to_another_company(self):
        """Copying a level accepts an explicit target company, and copies in batch."""
        other = self.env["res.company"].create({"name": "Other"})
        followup_10 = self.create_followup(delay=10)
        followup_40 = self.create_followup(delay=40)

        copied = followup_10.copy({"company_id": other.id})
        self.assertEqual(copied.company_id, other)
        self.assertEqual(copied.delay, 15, "no level there yet, so 0 + 15")

        batch = (followup_10 + followup_40).copy()
        self.assertEqual(batch.mapped("company_id"), self.env.company)
        self.assertEqual(
            batch.mapped("delay"),
            [55, 70],
            "offset past the highest delay, cumulatively",
        )

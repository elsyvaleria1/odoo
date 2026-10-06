from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import Form, tagged
from odoo.tools.misc import file_open

from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon
from odoo.addons.account_followup.tests.common import TestAccountFollowupCommon


@tagged("post_install", "-at_install")
class TestAccountFollowupReports(TestAccountReportsCommon, TestAccountFollowupCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.partner_a.email = "partner_a@mypartners.xyz"
        cls.report = cls.env.ref("account.followup_report")

    def test_followup_report_journal_option_disabled(self):
        self.report.filter_journals = False
        with patch.object(
            self.env.registry["report.formula"],
            "export_to_pdf",
            autospec=True,
            side_effect=lambda *args, **kwargs: {
                "file_name": "fake_partner_ledger.pdf",
                "file_content": b"",
                "file_type": "pdf",
            },
        ):
            self.partner_a._execute_followup_and_print(
                self.followup_request(self.partner_a, manual=True)
            )

    def test_followup_report_address_1(self):
        """Test child contact priorities: the company will be used when there is no followup or billing contacts"""

        Partner = self.env["res.partner"]
        self.partner_a.is_company = True

        child_partner = Partner.create(
            {
                "name": "Child contact",
                "type": "contact",
                "parent_id": self.partner_a.id,
            }
        )

        mail = self.env["mail.mail"].search([("recipient_ids", "=", self.partner_a.id)])
        self.init_invoice(
            "out_invoice",
            partner=child_partner,
            invoice_date="2016-01-01",
            amounts=[500],
            post=True,
        )
        self.partner_a._compute_unpaid_invoices()
        with patch.object(type(self.env["mail.mail"]), "unlink", lambda self: None):
            with patch.object(
                self.env.registry["report.formula"],
                "export_to_pdf",
                autospec=True,
                side_effect=lambda *args, **kwargs: {
                    "file_name": "fake_partner_ledger.pdf",
                    "file_content": b"",
                    "file_type": "pdf",
                },
            ):
                self.env["account.followup.report"]._send_email(
                    self.followup_request(self.partner_a)
                )

        mail = self.env["mail.mail"].search([("recipient_ids", "=", self.partner_a.id)])
        self.assertTrue(
            mail, "The payment reminder email should have been sent to the company."
        )

    def test_followup_report_address_2(self):
        """Test child contact priorities: the billing contact used on the invoice is preferred over a generic child contact."""

        Partner = self.env["res.partner"]
        self.partner_a.is_company = True

        # Testing followup sent to billing address if used in invoice

        child_partner = Partner.create(
            {
                "name": "Child contact",
                "type": "contact",
                "parent_id": self.partner_a.id,
            }
        )
        invoice_partner = Partner.create(
            {
                "name": "Child contact invoice",
                "type": "invoice",
                "email": "test-invoice@example.com",
                "parent_id": child_partner.id,
            }
        )

        self.init_invoice(
            "out_invoice",
            partner=invoice_partner,
            invoice_date="2016-01-01",
            amounts=[500],
            post=True,
        )

        self.partner_a._compute_unpaid_invoices()
        with patch.object(type(self.env["mail.mail"]), "unlink", lambda self: None):
            with patch.object(
                self.env.registry["report.formula"],
                "export_to_pdf",
                autospec=True,
                side_effect=lambda *args, **kwargs: {
                    "file_name": "fake_partner_ledger.pdf",
                    "file_content": b"",
                    "file_type": "pdf",
                },
            ):
                self.env["account.followup.report"]._send_email(
                    self.followup_request(self.partner_a)
                )

        mail = self.env["mail.mail"].search(
            [("recipient_ids", "=", invoice_partner.id)]
        )
        self.assertTrue(
            mail,
            "The payment reminder email should have been sent to the invoice partner.",
        )
        mail.unlink()

    def test_negative_followup_report(self):
        """Test negative or null followup reports: if a contact has an overdue invoice but has a negative or null total due, no action is needed."""
        followup_line = self.env["account_followup.followup.line"].create(
            {
                "company_id": self.env.company.id,
                "name": "First Reminder",
                "delay": 15,
                "send_email": False,
            }
        )
        self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2016-01-01",
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
        ).action_post()

        self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "invoice_date": "2016-01-15",
                "partner_id": self.partner_a.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "quantity": 1,
                            "price_unit": 300,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        ).action_post()
        self.assertEqual(self.partner_a.total_due, 200)
        self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_line)

        self.env["account.payment"].create(
            {
                "partner_id": self.partner_a.id,
                "amount": 400,
            }
        ).action_post()
        self.assertEqual(self.partner_a.total_due, -200)
        self.assertPartnerFollowup(self.partner_a, "no_action_needed", followup_line)

    def test_followup_send_email(self):
        """Tests that the email address in the mail.template is used to send the followup email."""
        self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2016-01-01",
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
        ).action_post()

        def send_email(email_from, marker):
            """Create a mail.template, open the followup wizard, send, and return the message."""
            mail_template = self.env["mail.template"].create(
                {
                    "name": "Payment Reminder",
                    "model_id": self.env.ref("base.model_res_partner").id,
                    "email_from": email_from,
                    "partner_to": "{{ object.id }}",
                    "subject": "{{ (object.company_id or object._get_followup_responsible().company_id).name }} "
                    + marker,
                }
            )
            wizard = (
                self.env["wizard.res.partner.send.followup"]
                .with_context(
                    active_model="res.partner",
                    active_ids=self.partner_a.ids,
                )
                .create({})
            )
            wizard.email = True  # tick the 'email' checkbox
            wizard.template_id = mail_template
            with patch.object(
                self.env.registry["report.formula"],
                "export_to_pdf",
                autospec=True,
                side_effect=lambda *args, **kwargs: {
                    "file_name": "fake_partner_ledger.pdf",
                    "file_content": b"",
                    "file_type": "pdf",
                },
            ):
                wizard.process_followup()
            message = self.env["mail.message"].search([("subject", "like", marker)])
            self.assertEqual(len(message), 1)
            self.assertEqual(message.author_id, self.env.user.partner_id)
            return message

        # case 1: the email_from is dynamically set
        message = send_email(
            email_from="{{ object._get_followup_responsible().email_formatted }}",
            marker="Pay me now !",
        )
        self.assertEqual(message.email_from, self.env.user.partner_id.email_formatted)

        # case 2: the email_from is hardcoded in the template
        message = send_email(email_from="test@odoo.com", marker="Pay me noooow !")
        self.assertEqual(message.email_from, "test@odoo.com")

    def test_process_automatic_followup_send_email(self):
        """Tests that the email address in the mail.template is used to send the followup email from the cron."""
        self.env["account_followup.followup.line"].create(
            {
                "company_id": self.env.company.id,
                "name": "First Reminder",
                "delay": 15,
                "send_email": True,
            }
        )
        self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2016-01-01",
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
        ).action_post()

        def send_email(email_from, marker):
            """Create a mail.template, link it to the followup line, execute, return the message."""
            mail_template = self.env["mail.template"].create(
                {
                    "name": "Payment Reminder",
                    "model_id": self.env.ref("base.model_res_partner").id,
                    "email_from": email_from,
                    "partner_to": "{{ object.id }}",
                    "subject": "{{ (object.company_id or object._get_followup_responsible().company_id).name }} "
                    + marker,
                }
            )
            self.partner_a.followup_line_id.mail_template_id = mail_template
            self.partner_a.followup_next_action_date = False
            with patch.object(
                self.env.registry["report.formula"],
                "export_to_pdf",
                autospec=True,
                side_effect=lambda *args, **kwargs: {
                    "file_name": "fake_partner_ledger.pdf",
                    "file_content": b"",
                    "file_type": "pdf",
                },
            ):
                self.partner_a._execute_followup(self.followup_request(self.partner_a))
            message = self.env["mail.message"].search([("subject", "like", marker)])
            self.assertEqual(len(message), 1)
            self.assertEqual(
                message.author_id,
                self.partner_a._get_followup_responsible().partner_id,
                "Automatic followups should have the followup responsible as the author.",
            )
            return message

        # case 1: the email_from is dynamically set
        message = send_email(
            email_from="{{ object._get_followup_responsible().email_formatted }}",
            marker="Pay me now !",
        )
        self.assertEqual(message.email_from, self.env.user.partner_id.email_formatted)

        # we have to create a new overdue invoice to test the second case as the previous invoice
        # will no longer trigger the followup
        self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2016-01-01",
                "partner_id": self.partner_a.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "quantity": 1,
                            "price_unit": 600,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        ).action_post()

        # case 2: the email_from is hardcoded in the template
        message = send_email(email_from="test@odoo.com", marker="Pay me noooow !")
        self.assertEqual(message.email_from, "test@odoo.com")

    def test_compute_render_model(self):
        with Form(
            self.env["wizard.res.partner.send.followup"].with_context(
                active_model="res.partner",
                active_ids=self.partner_a.ids,
            )
        ) as wizard:
            self.assertEqual(wizard.render_model, "res.partner")

    def test_followup_report_with_levels_on_main_company(self):
        cron = self.env.ref("account_followup.ir_cron_follow_up")

        self.env["account_followup.followup.line"].create(
            [
                {
                    "company_id": self.company_data["company"].id,
                    "name": "First Reminder",
                    "delay": 15,
                    "send_email": True,
                    "auto_execute": True,
                },
                {
                    "company_id": self.company_data["company"].id,
                    "name": "Second Reminder",
                    "delay": 30,
                    "send_email": True,
                    "auto_execute": True,
                },
            ]
        )

        self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2016-01-01",
                "invoice_date_due": "2016-01-01",
                "date": "2016-01-01",
                "partner_id": self.partner_a.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "quantity": 1,
                            "price_unit": 500,
                        }
                    )
                ],
            }
        ).action_post()

        with (
            freeze_time("2022-01-10"),
            patch.object(self.env.registry["res.partner"], "_send_followup") as patched,
            self.sync_env_with_side_cursors(),
            patch.object(
                self.env.registry["ir.actions.report"],
                "_render_html_to_pdf",
                return_value=b"0",
            ),
        ):
            cron.method_direct_trigger()
            # For the same reason we clear the cache in assertPartnerFollowup, to avoid this test change the state of the cache,
            # which could break other tests.
            self.assertEqual(patched.call_count, 1)

        count_mail = self.env["mail.message"].search_count(
            [("record_company_id", "=", self.company_data["company"].id)]
        )
        # We should have 1 email :
        # 1 for the main company
        self.assertEqual(count_mail, 1)

    def test_followup_report_with_levels_on_one_branch(self):
        cron = self.env.ref("account_followup.ir_cron_follow_up")

        branch_a, branch_b = self.env["res.company"].create(
            [
                {
                    "name": "Branch number 1",
                    "parent_id": self.company_data["company"].id,
                },
                {
                    "name": "Branch number 2",
                    "parent_id": self.company_data["company"].id,
                },
            ]
        )

        self.cr.precommit.run()  # load the COA

        self.env["account_followup.followup.line"].create(
            [
                {
                    "company_id": branch_a.id,
                    "name": "First Reminder (A)",
                    "delay": 15,
                    "send_email": True,
                    "auto_execute": True,
                },
                {
                    "company_id": branch_a.id,
                    "name": "Second Reminder (A)",
                    "delay": 30,
                    "send_email": True,
                    "auto_execute": True,
                },
            ]
        )

        self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "invoice_date": "2016-01-01",
                    "invoice_date_due": "2016-01-01",
                    "date": "2016-01-01",
                    "partner_id": self.partner_a.id,
                    "company_id": branch_a.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "quantity": 1,
                                "price_unit": 400,
                            }
                        )
                    ],
                },
                {
                    "move_type": "out_invoice",
                    "invoice_date": "2016-01-01",
                    "invoice_date_due": "2016-01-01",
                    "date": "2016-01-01",
                    "partner_id": self.partner_a.id,
                    "company_id": branch_b.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "quantity": 1,
                                "price_unit": 800,
                            }
                        )
                    ],
                },
            ]
        ).action_post()

        with (
            freeze_time("2022-01-10"),
            patch.object(self.env.registry["res.partner"], "_send_followup") as patched,
            self.sync_env_with_side_cursors(),
            patch.object(
                self.env.registry["ir.actions.report"],
                "_render_html_to_pdf",
                return_value=b"0",
            ),
        ):
            cron.method_direct_trigger()
            # For the same reason we clear the cache in assertPartnerFollowup, to avoid this test change the state of the cache,
            # which could break other tests.
            self.assertEqual(patched.call_count, 1)

        count_mail = self.env["mail.message"].search_count(
            [("record_company_id", "=", branch_a.id)]
        )
        # We should have 1 email :
        # 1 for the Branch number 1
        self.assertEqual(count_mail, 1)

    def test_followup_report_with_levels_on_branches_and_main_company(self):
        cron = self.env.ref("account_followup.ir_cron_follow_up")

        branch_a, branch_b = self.env["res.company"].create(
            [
                {
                    "name": "Branch number 1",
                    "parent_id": self.company_data["company"].id,
                },
                {
                    "name": "Branch number 2",
                    "parent_id": self.company_data["company"].id,
                },
            ]
        )

        self.cr.precommit.run()  # load the COA

        self.env["account_followup.followup.line"].create(
            [
                {
                    "company_id": branch_a.id,
                    "name": "First Reminder (A)",
                    "delay": 15,
                    "send_email": True,
                    "auto_execute": True,
                },
                {
                    "company_id": branch_a.id,
                    "name": "Second Reminder (A)",
                    "delay": 30,
                    "send_email": True,
                    "auto_execute": True,
                },
                {
                    "company_id": branch_b.id,
                    "name": "First Reminder (B)",
                    "delay": 10,
                    "send_email": True,
                    "auto_execute": True,
                },
                {
                    "company_id": branch_b.id,
                    "name": "Second Reminder (B)",
                    "delay": 20,
                    "send_email": True,
                    "auto_execute": True,
                },
                {
                    "company_id": self.company_data["company"].id,
                    "name": "First Reminder",
                    "delay": 20,
                    "send_email": True,
                    "auto_execute": True,
                },
                {
                    "company_id": self.company_data["company"].id,
                    "name": "Second Reminder",
                    "delay": 40,
                    "send_email": True,
                    "auto_execute": True,
                },
            ]
        )

        self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "invoice_date": "2016-01-01",
                    "invoice_date_due": "2016-01-01",
                    "date": "2016-01-01",
                    "partner_id": self.partner_a.id,
                    "company_id": branch_a.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "quantity": 1,
                                "price_unit": 400,
                            }
                        )
                    ],
                },
                {
                    "move_type": "out_invoice",
                    "invoice_date": "2016-01-01",
                    "invoice_date_due": "2016-01-01",
                    "date": "2016-01-01",
                    "partner_id": self.partner_a.id,
                    "company_id": branch_b.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "quantity": 1,
                                "price_unit": 800,
                            }
                        )
                    ],
                },
                {
                    "move_type": "out_invoice",
                    "invoice_date": "2016-01-01",
                    "invoice_date_due": "2016-01-01",
                    "date": "2016-01-01",
                    "partner_id": self.partner_a.id,
                    "company_id": self.company_data["company"].id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "quantity": 1,
                                "price_unit": 200,
                            }
                        )
                    ],
                },
            ]
        ).action_post()

        with (
            freeze_time("2022-01-10"),
            patch.object(self.env.registry["res.partner"], "_send_followup") as patched,
            self.sync_env_with_side_cursors(),
            patch.object(
                self.env.registry["ir.actions.report"],
                "_render_html_to_pdf",
                return_value=b"0",
            ),
        ):
            cron.method_direct_trigger()
            # For the same reason we clear the cache in assertPartnerFollowup, to avoid this test change the state of the cache,
            # which could break other tests.
            self.assertEqual(patched.call_count, 3)

        count_mail = self.env["mail.message"].search_count(
            [
                (
                    "record_company_id",
                    "in",
                    [self.company_data["company"].id, branch_a.id, branch_b.id],
                )
            ]
        )
        # We should have 3 emails :
        # 1 for the main company
        # 1 for the Branch number 1
        # 1 for the Branch number 2
        self.assertEqual(count_mail, 3)

        # Now we check the amounts overdue
        # Expected : 200 (main_company) + 400 (branch_a) + 800 (branch_b)
        self.assertEqual(self.partner_a.total_overdue, 1400)
        # Expected : 400
        self.assertEqual(self.partner_a.with_company(branch_a).total_overdue, 400)
        # Expected : 800
        self.assertEqual(self.partner_a.with_company(branch_b).total_overdue, 800)

    def test_partner_total_due_with_payable(self):
        """
        Test that the total due for a partner also reflects payable accounts and is coherent with the customer statement report.
        """
        # Init options.
        report = self.env.ref("account.customer_statement_report")
        default_options = {
            "partner_id": self.partner_a.id,
            "multi_currency": True,
            "unfold_all": True,
        }
        options = self._generate_options(
            report,
            fields.Date.from_string("2016-01-01"),
            fields.Date.from_string("2016-12-31"),
            default_options=default_options,
        )

        invoice = self.init_invoice(
            "out_invoice", self.partner_a, "2016-01-01", True, amounts=[500]
        )

        self.assertRecordValues(
            self.partner_a, [{"total_due": 500.0, "total_net_due": 500.0}]
        )

        with freeze_time("2016-01-01"):
            self.assertLinesValues(
                # pylint: disable=C0326
                report._get_lines(options),
                #   Name                                        Date,        Due Date,  Amount,       Balance
                [0, 1, 2, 3, 5],
                [
                    ("partner_a", "", "", 500.0, 500.0),
                    (invoice.name, "01/01/2016", "01/01/2016", 500.0, 500.0),
                    ("Total partner_a", "", "", 500.0, 500.0),
                    ("Total", "", "", 500.0, 500.0),
                ],
                options,
            )

        bill = self.init_invoice(
            "in_invoice", self.partner_a, "2016-01-01", True, amounts=[200]
        )

        self.assertRecordValues(
            self.partner_a, [{"total_due": 500.0, "total_net_due": 300.0}]
        )

        with freeze_time("2016-01-01"):
            self.assertLinesValues(
                # pylint: disable=C0326
                report._get_lines(options),
                #   Name                                        Date,        Due Date,  Amount,       Balance
                [0, 1, 2, 3, 5],
                [
                    ("partner_a", "", "", 300.0, 300.0),
                    (invoice.name, "01/01/2016", "01/01/2016", 500.0, 500.0),
                    (bill.name, "01/01/2016", "01/01/2016", -200.0, 300.0),
                    ("Total partner_a", "", "", 300.0, 300.0),
                    ("Total", "", "", 300.0, 300.0),
                ],
                options,
            )

    def test_automatic_followup_report_attachments(self):
        followup_line = self.env["account_followup.followup.line"].create(
            {
                "company_id": self.env.company.id,
                "name": "First Reminder",
                "delay": 15,
                "send_email": True,
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2016-01-01",
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
        )
        invoice.action_post()

        self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_line)

        invoice_attachment = self.env["ir.attachment"].create(
            {
                "name": "some_attachment.pdf",
                "res_id": invoice.id,
                "res_model": "account.move",
                "datas": "test",
                "type": "binary",
            }
        )
        invoice._message_set_main_attachment_id(invoice_attachment)

        self.partner_a._compute_unpaid_invoices()
        with patch.object(
            self.env.registry["report.formula"],
            "export_to_pdf",
            autospec=True,
            side_effect=lambda *args, **kwargs: {
                "file_name": "fake_partner_ledger.pdf",
                "file_content": b"",
                "file_type": "pdf",
            },
        ):
            self.partner_a.action_manually_process_automatic_followups()

        sent_attachments = (
            self.env["mail.message"]
            .search([("partner_ids", "=", self.partner_a.id)])
            .attachment_ids
        )
        self.assertEqual(
            sent_attachments.mapped("name"),
            [f"{self.partner_a.name} - fake_partner_ledger.pdf", "some_attachment.pdf"],
        )

    def test_manual_followup_report_invoices_removed(self):
        followup_line = self.env["account_followup.followup.line"].create(
            {
                "company_id": self.env.company.id,
                "name": "First Reminder",
                "delay": 15,
                "send_email": True,
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2016-01-01",
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
        )
        invoice.action_post()

        self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_line)

        invoice_attachment = self.env["ir.attachment"].create(
            {
                "name": "some_attachment.pdf",
                "res_id": invoice.id,
                "res_model": "account.move",
                "datas": "test",
                "type": "binary",
            }
        )
        invoice._message_set_main_attachment_id(invoice_attachment)

        self.partner_a._compute_unpaid_invoices()
        with patch.object(
            self.env.registry["report.formula"],
            "export_to_pdf",
            autospec=True,
            side_effect=lambda *args, **kwargs: {
                "file_name": "fake_partner_ledger.pdf",
                "file_content": b"",
                "file_type": "pdf",
            },
        ):
            self.partner_a._execute_followup(
                self.followup_request(
                    self.partner_a, manual=True, join_invoices=True, attachment_ids=[]
                )
            )

        sent_attachments = (
            self.env["mail.message"]
            .search([("partner_ids", "=", self.partner_a.id)])
            .attachment_ids
        )
        self.assertEqual(
            sent_attachments.mapped("name"),
            [f"{self.partner_a.name} - fake_partner_ledger.pdf"],
        )

    def test_manual_followup_report_join_invoices(self):
        followup_line = self.env["account_followup.followup.line"].create(
            {
                "company_id": self.env.company.id,
                "name": "First Reminder",
                "delay": 15,
                "send_email": True,
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2016-01-01",
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
        )
        invoice.action_post()

        self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_line)

        invoice_attachment = self.env["ir.attachment"].create(
            {
                "name": "some_attachment.pdf",
                "res_id": invoice.id,
                "res_model": "account.move",
                "datas": "test",
                "type": "binary",
            }
        )
        invoice._message_set_main_attachment_id(invoice_attachment)

        self.partner_a._compute_unpaid_invoices()
        with patch.object(
            self.env.registry["report.formula"],
            "export_to_pdf",
            autospec=True,
            side_effect=lambda *args, **kwargs: {
                "file_name": "fake_partner_ledger.pdf",
                "file_content": b"",
                "file_type": "pdf",
            },
        ):
            self.partner_a._execute_followup(
                self.followup_request(
                    self.partner_a,
                    manual=True,
                    join_invoices=False,
                    attachment_ids=invoice_attachment.ids,
                )
            )

        sent_attachments = (
            self.env["mail.message"]
            .search([("partner_ids", "=", self.partner_a.id)])
            .attachment_ids
        )
        self.assertEqual(
            sent_attachments.mapped("name"),
            [f"{self.partner_a.name} - fake_partner_ledger.pdf"],
        )

    def test_action_report_followup(self):
        def _render_html_to_pdf(_self, bodies, *args, _split=False, **kwargs):
            # Same contract as the method it stands in for: one merged PDF, or
            # one per body under `_split`. Returning the bytes either way makes
            # the split caller iterate them as ints.
            pdf = file_open("base/tests/minimal.pdf", "rb").read()
            return [pdf] * len(bodies) if _split else pdf

        followup_line = self.env["account_followup.followup.line"].create(
            {
                "company_id": self.env.company.id,
                "name": "First Reminder",
                "delay": 15,
                "send_email": True,
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2016-01-01",
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
        )
        invoice.action_post()

        self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_line)

        with patch.object(
            self.env.registry["ir.actions.report"],
            "_render_html_to_pdf",
            _render_html_to_pdf,
        ):
            followup_letter = (
                self.env["ir.actions.report"]
                .with_context(force_report_rendering=True)
                ._render_qweb_pdf(
                    "account_followup.report_followup_print_all", self.partner_a.id
                )[0]
            )
        self.assertTrue(followup_letter)

    def test_automatic_followup_report_attachments_from_template(self):
        mail_template = self.env["mail.template"].create(
            {
                "name": "reminder",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "email_cc": "john.carmac@example.me",
            }
        )
        template_attachment = self.env["ir.attachment"].create(
            {
                "name": "template_attachment.pdf",
                "res_id": mail_template.id,
                "res_model": "mail.template",
                "datas": "test",
                "type": "binary",
            }
        )
        mail_template.attachment_ids = [template_attachment.id]

        dynamic_report = self.env["ir.actions.report"].create(
            {
                "name": "Test Report Partner",
                "model": "res.partner",
                "report_name": "account_followup.report_followup_print_all",
                "print_report_name": "'followup_dynamic_report'",
            }
        )
        mail_template.report_template_ids = [dynamic_report.id]

        followup_line = self.env["account_followup.followup.line"].create(
            {
                "company_id": self.env.company.id,
                "name": "First Reminder",
                "delay": 15,
                "send_email": True,
                "mail_template_id": mail_template.id,
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2016-01-01",
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
        )
        invoice.action_post()
        self.assertPartnerFollowup(self.partner_a, "in_need_of_action", followup_line)

        invoice_attachment = self.env["ir.attachment"].create(
            {
                "name": "invoice_attachment.pdf",
                "res_id": invoice.id,
                "res_model": "account.move",
                "datas": "test",
                "type": "binary",
            }
        )
        invoice._message_set_main_attachment_id(invoice_attachment)

        self.partner_a._compute_unpaid_invoices()
        with patch.object(
            self.env.registry["report.formula"],
            "export_to_pdf",
            autospec=True,
            side_effect=lambda *args, **kwargs: {
                "file_name": "fake_partner_ledger.pdf",
                "file_content": b"",
                "file_type": "pdf",
            },
        ):
            self.partner_a.action_manually_process_automatic_followups()

        sent_attachments = (
            self.env["mail.message"]
            .search([("partner_ids", "=", self.partner_a.id)])
            .attachment_ids
        )
        self.assertEqual(
            sorted(sent_attachments.mapped("name")),
            sorted(
                [
                    f"{self.partner_a.name} - fake_partner_ledger.pdf",
                    "template_attachment.pdf",
                    "followup_dynamic_report.html",
                    "invoice_attachment.pdf",
                ]
            ),
        )

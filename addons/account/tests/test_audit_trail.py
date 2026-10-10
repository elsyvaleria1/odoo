import logging
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.orm.runtime.backend import COPY_THRESHOLD
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import (
    AccountTestInvoicingCommon,
    AccountTestInvoicingHttpCommon,
)

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestAuditTrail(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = (
            cls.env["base"]
            .with_context(
                tracking_disable=False,
                mail_create_nolog=False,
                mail_notrack=False,
            )
            .env
        )
        cls.env.company.account_config_id.restrictive_audit_trail = False
        cls.move = cls.create_move()

    @classmethod
    def create_move(cls):
        return cls.env["account.move"].create(
            {
                "date": "2021-04-01",
                "line_ids": [
                    Command.create(
                        {
                            "balance": 100,
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                        }
                    ),
                    Command.create(
                        {
                            "balance": -100,
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                        }
                    ),
                ],
            }
        )

    def get_trail(self, record):
        self.env.cr.precommit.run()
        return self.env["mail.message"].search(
            [
                ("model", "=", record._name),
                ("res_id", "=", record.id),
            ]
        )

    def assertTrail(self, trail, expected):
        self.assertEqual(len(trail), len(expected))
        for message, expected_needle in zip(trail, expected[::-1], strict=False):
            self.assertIn(expected_needle, message.account_audit_log_preview)

    def test_can_unlink_draft(self):
        self.env.company.account_config_id.restrictive_audit_trail = True
        self.env.cr.precommit.run()
        self.assertTrue(self.get_trail(self.move))
        self.env.invalidate_all()
        self.move.unlink()
        self.assertFalse(self.get_trail(self.move))

    def test_forcing_the_delete_of_a_posted_move_keeps_its_trail(self):
        self.env.company.account_config_id.restrictive_audit_trail = True
        self.move.action_post()
        self.move.action_draft()
        with self.assertRaisesRegex(
            UserError, "remove parts of a restricted audit trail"
        ):
            self.move.with_context(force_delete=True).unlink()
        self.assertTrue(self.move.exists())

    def test_cant_unlink_posted(self):
        self.env.company.account_config_id.restrictive_audit_trail = True
        self.move.action_post()
        self.move.action_draft()
        with self.assertRaisesRegex(
            UserError, "remove parts of a restricted audit trail"
        ):
            self.move.unlink()

    def test_cant_unlink_message(self):
        self.env.company.account_config_id.restrictive_audit_trail = True
        self.move.action_post()
        self.env.cr.flush()
        audit_trail = self.get_trail(self.move)
        with self.assertRaisesRegex(
            UserError, "remove parts of a restricted audit trail"
        ):
            audit_trail.unlink()

    def test_cant_unown_message(self):
        self.env.company.account_config_id.restrictive_audit_trail = True
        self.move.action_post()
        self.env.cr.flush()
        audit_trail = self.get_trail(self.move)
        with self.assertRaisesRegex(
            UserError, "remove parts of a restricted audit trail"
        ):
            audit_trail.res_id = 0

    def test_cant_unlink_tracking_value(self):
        self.env.company.account_config_id.restrictive_audit_trail = True
        self.move.action_post()
        self.env.cr.precommit.run()
        self.move.name = "track this!"
        audit_trail = self.get_trail(self.move)
        trackings = audit_trail.tracking_value_ids.sudo()
        self.assertTrue(trackings)
        with self.assertRaisesRegex(
            UserError, "remove parts of a restricted audit trail"
        ):
            trackings.unlink()

    def test_content(self):
        messages = ["Journal Entry created"]
        self.assertTrail(self.get_trail(self.move), messages)

        self.move.action_post()
        messages.append(
            "Updated\nFalse ⇨ True (Reviewed)\nFalse ⇨ MISC/2021/04/0001 (Number)\nDraft ⇨ Posted (Status)"
        )
        self.assertTrail(self.get_trail(self.move), messages)

        self.move.action_draft()
        messages.append("Updated\nTrue ⇨ False (Reviewed)\nPosted ⇨ Draft (Status)")
        self.assertTrail(self.get_trail(self.move), messages)

        self.move.name = "nawak"
        messages.append("Updated\nMISC/2021/04/0001 ⇨ nawak (Number)")
        self.assertTrail(self.get_trail(self.move), messages)

        self.move.line_ids = [
            Command.update(self.move.line_ids[0].id, {"balance": 300}),
            Command.update(self.move.line_ids[1].id, {"credit": 200}),
            Command.create(
                {
                    "balance": -100,
                    "account_id": self.company_data["default_account_revenue"].id,
                }
            ),
        ]
        messages.extend(
            [
                "updated\n100.0 ⇨ 300.0",
                "updated\n-100.0 ⇨ -200.0",
                "created\n ⇨ 400000 Product Sales (Account)\n0.0 ⇨ -100.0 (Balance)",
            ]
        )
        self.assertTrail(self.get_trail(self.move), messages)

        self.move.line_ids[
            0
        ].tax_ids = self.env.company.tax_config_id.account_purchase_tax_id
        suspense_account_code = (
            self.env.company.account_config_id.account_journal_suspense_account_id.code
        )
        messages.extend(
            [
                "updated\n ⇨ 15% (Taxes)",
                "created\n ⇨ 131000 Tax Paid (Account)\n0.0 ⇨ 45.0 (Balance)\nFalse ⇨ 15% (Label)",
                f"created\n ⇨ {suspense_account_code} Bank Suspense Account (Account)\n0.0 ⇨ -45.0 (Balance)\nFalse ⇨ Automatic Balancing Line (Label)",
            ]
        )
        self.assertTrail(self.get_trail(self.move), messages)
        self.move.with_context(dynamic_unlink=True).line_ids.unlink()
        messages.extend(
            [
                "deleted\n400000 Product Sales ⇨  (Account)\n300.0 ⇨ 0.0 (Balance)\n15% ⇨  (Taxes)",
                "deleted\n400000 Product Sales ⇨  (Account)\n-200.0 ⇨ 0.0 (Balance)",
                "deleted\n400000 Product Sales ⇨  (Account)\n-100.0 ⇨ 0.0 (Balance)",
                "deleted\n131000 Tax Paid ⇨  (Account)\n45.0 ⇨ 0.0 (Balance)\n15% ⇨ False (Label)",
                f"deleted\n{suspense_account_code} Bank Suspense Account ⇨  (Account)\n-45.0 ⇨ 0.0 (Balance)\nAutomatic Balancing Line ⇨ False (Label)",
            ]
        )
        self.assertTrail(self.get_trail(self.move), messages)

        # the configuration's earlier history (its creation log, written or
        # not depending on the context that first asked for it) is not the
        # trail of this change
        config = self.env.company.account_config_id
        before = self.get_trail(config)
        config.restrictive_audit_trail = True
        messages_company = ["Updated\nFalse ⇨ True (Restrictive Audit Trail)"]
        self.assertTrail(self.get_trail(config) - before, messages_company)

    def _posted_move_with_lines(self, line_count):
        revenue = self.company_data["default_account_revenue"]
        move = self.env["account.move"].create(
            {
                "date": "2021-04-01",
                "line_ids": [
                    Command.create(
                        {"balance": 10, "account_id": revenue.id, "name": f"d{index}"}
                    )
                    for index in range(line_count)
                ]
                + [
                    Command.create(
                        {"balance": -10 * line_count, "account_id": revenue.id}
                    )
                ],
            }
        )
        move.action_post()
        self.get_trail(move)
        return move, move.line_ids.filtered(lambda line: line.balance > 0)

    def test_posted_line_edits_log_one_message_per_journal_item(self):
        self.env.company.account_config_id.restrictive_audit_trail = True
        move, lines = self._posted_move_with_lines(20)
        before = self.get_trail(move)

        lines.write({"name": "renamed"})

        trail = self.get_trail(move) - before
        self.assertEqual(len(trail), len(lines))
        for index, (line, message) in enumerate(
            zip(lines.sorted("id"), trail.sorted("id"), strict=True)
        ):
            self.assertIn(f'data-oe-id="{line.id}"', str(message.body))
            self.assertEqual(
                message.account_audit_log_preview,
                f"Journal Item #{line.id} updated\nd{index} ⇨ renamed (Label)",
            )
            trackings = message.sudo().tracking_value_ids
            self.assertEqual(
                (
                    trackings.field_id.name,
                    trackings.old_value_char,
                    trackings.new_value_char,
                ),
                ("name", f"d{index}", "renamed"),
            )
            self.assertEqual(message.subtype_id, self.env.ref("mail.mt_note"))
            self.assertEqual(message.message_type, "notification")
            self.assertTrue(message.account_audit_log_restricted)
        self.assertFalse(trail.notification_ids)

    def test_posted_line_edits_log_in_constant_queries(self):
        sizes = (20, COPY_THRESHOLD - 1, COPY_THRESHOLD, 2 * COPY_THRESHOLD)
        lines = {size: self._posted_move_with_lines(size)[1] for size in sizes}

        def rename(size):
            lines[size].write({"name": "renamed"})

        self.assertQueriesConstant(rename, small=sizes[0], large=sizes[1])
        self.assertQueriesConstant(rename, small=sizes[2], large=sizes[3])

    def test_preview_hides_what_the_chatter_hides(self):
        self.get_trail(self.move)
        self.move.action_post()
        posted = self.get_trail(self.move).filtered(
            lambda message: "(Status)" in message.account_audit_log_preview
        )
        self.assertEqual(len(posted), 1)

        def _track_filtered_for_display(move, tracking_values):
            return tracking_values.filtered(lambda t: t.field_id.name != "state")

        self.patch(
            self.registry["account.move"],
            "_track_filtered_for_display",
            _track_filtered_for_display,
        )
        posted.invalidate_recordset(["account_audit_log_preview"])
        self.assertNotIn("(Status)", posted.account_audit_log_preview)
        self.assertIn("(Number)", posted.account_audit_log_preview)

    def test_partner_notif(self):
        user = new_test_user(
            self.env,
            "test-user-notif",
            groups="base.group_portal",
            notification_type="email",
        )
        user.partner_id.sudo().customer_rank += 1
        self.assertGreater(user.partner_id.customer_rank, 0)
        user.partner_id.message_post(body="Test", partner_ids=user.partner_id.ids)

    def test_partner_unlink(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Test",
                "customer_rank": 1,
            }
        )
        partner.unlink()

    def test_an_author_without_accounting_rights_edits_their_note(self):
        self.env.company.account_config_id.restrictive_audit_trail = True
        employee = new_test_user(
            self.env,
            "test-audit-employee",
            groups="base.group_user,base.group_partner_manager",
        )
        partner = self.env["res.partner"].create({"name": "Audit Neighbour"})
        partner = partner.with_user(employee)
        message = partner.message_post(body="Tpyo", message_type="comment")

        partner._message_update_content(message, body="Typo")

        self.assertIn("Typo", str(message.body))
        self.assertFalse(message.account_audit_log_restricted)


@tagged("post_install", "-at_install")
class TestAuditTrailAttachment(AccountTestInvoicingHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.account_config_id.restrictive_audit_trail = True
        cls.document_installed = (
            "documents_account"
            in cls.env["ir.module.module"]._get_installed_module_ids()
        )
        if cls.document_installed:
            folder_test = cls.env["document.document"].create(
                {
                    "name": "folder_test",
                    "type": "folder",
                }
            )
            existing_setting = (
                cls.env["document.account.folder.setting"]
                .sudo()
                .search(
                    [("journal_id", "=", cls.company_data["default_journal_sale"].id)]
                )
            )
            if existing_setting:
                existing_setting.folder_id = folder_test
            else:
                cls.env["document.account.folder.setting"].sudo().create(
                    {
                        "folder_id": folder_test.id,
                        "journal_id": cls.company_data["default_journal_sale"].id,
                    }
                )

    def _send_and_print(self, invoice):
        return (
            self.env["mixin.account.move.send"]
            .with_context(
                force_report_rendering=True,
            )
            ._generate_and_send_invoices(invoice)
        )

    def test_audit_trail_attachment(self):
        invoice = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "product",
                                "quantity": 1,
                                "price_unit": 100,
                            }
                        )
                    ],
                }
            ]
        )
        invoice.action_post()
        self.assertFalse(invoice.message_main_attachment_id)

        first_attachment = self._send_and_print(invoice)
        self.assertTrue(first_attachment)

        first_attachment.unlink()
        self.assertTrue(first_attachment.exists())
        with self.assertRaisesRegex(
            UserError, "remove parts of a restricted audit trail."
        ):
            first_attachment.unlink()

        invoice.invalidate_recordset()
        second_attachment = self._send_and_print(invoice)
        self.assertNotEqual(first_attachment, second_attachment)

        first_attachment.register_as_main_attachment()
        self.assertEqual(invoice.message_main_attachment_id, first_attachment)
        second_attachment.register_as_main_attachment()
        self.assertEqual(invoice.message_main_attachment_id, second_attachment)

        if self.document_installed:
            document = self.env["document.document"].search(
                [
                    ("res_model", "=", "account.move"),
                    ("res_id", "=", invoice.id),
                    ("name", "=ilike", "%.pdf"),
                ]
            )
            self.assertTrue(document)
            document.attachment_id = first_attachment
            document.attachment_id = second_attachment
        else:
            _logger.runbot(
                "Documents module is not installed, skipping part of the test"
            )

    def test_a_large_xml_document_is_part_of_the_audit_trail(self):
        # past the 2 KB a head-only sniff reads, an XML once typed as text and
        # slipped out of the trail
        self.env.company.account_config_id.restrictive_audit_trail = True
        invoice = self.init_invoice("out_invoice", amounts=[100], post=True)
        lines = "".join(f'<Line n="{n}">{"x" * 40}</Line>' for n in range(80))
        xml = self.env["ir.attachment"].create(
            {
                "name": "invoice.xml",
                "raw": f'<?xml version="1.0"?><Invoice>{lines}</Invoice>'.encode(),
                "res_model": "account.move",
                "res_id": invoice.id,
            }
        )
        self.assertGreater(len(xml.raw), 2048)
        with self.assertRaisesRegex(
            UserError, "remove parts of a restricted audit trail."
        ):
            xml.write({"res_model": "res.partner", "res_id": self.partner_a.id})

    def test_audit_trail_write_attachment(self):
        invoice = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "product",
                                "quantity": 1,
                                "price_unit": 100,
                            }
                        )
                    ],
                }
            ]
        )
        invoice.action_post()
        self.assertFalse(invoice.message_main_attachment_id)

        self._send_and_print(invoice)
        attachment = invoice.message_main_attachment_id

        with self.assertRaisesRegex(
            UserError, "remove parts of a restricted audit trail."
        ):
            attachment.write(
                {
                    "res_id": self.env.user.id,
                    "res_model": self.env.user._name,
                }
            )

        with self.assertRaisesRegex(
            UserError, "remove parts of a restricted audit trail."
        ):
            attachment.datas = b"new data"

        another_attachment = self.env["ir.attachment"].create(
            {
                "name": "doc.pdf",
                "res_model": "wizard.mail.message.send",
                "datas": attachment.datas,
            }
        )
        invoice.message_post(
            message_type="comment", attachment_ids=another_attachment.ids
        )


@tagged("post_install", "-at_install")
class TestAuditTrailAttachmentCompany(AccountTestInvoicingCommon):
    PDF = b"%PDF-1.4\n%audit trail\n"

    def _attach(self, invoice, company, **vals):
        return self.env["ir.attachment"].create(
            {
                "name": "invoice.pdf",
                "raw": self.PDF,
                "res_model": "account.move",
                "res_id": invoice.id,
                "company_id": company.id,
                **vals,
            }
        )

    def test_the_invoice_pdf_follows_the_audit_trail_of_its_move_company(self):
        company_a = self.env.company
        company_a.account_config_id.restrictive_audit_trail = False
        company_data_b = self.setup_other_company(name="audit_company_b")
        company_b = company_data_b["company"]
        company_b.account_config_id.restrictive_audit_trail = True
        invoice = self.init_invoice(
            "out_invoice", amounts=[100], post=True, company=company_b
        )
        pdf = self._attach(invoice, company_a, res_field="invoice_pdf_report_file")

        pdf.unlink()

        self.assertTrue(pdf.exists(), "the PDF of a restricted move is detached")
        self.assertFalse(pdf.res_field)

    def test_an_unrestricted_company_never_reads_the_attachment_content(self):
        self.env.company.account_config_id.restrictive_audit_trail = False
        invoice = self.init_invoice("out_invoice", amounts=[100], post=True)
        attachments = self.env["ir.attachment"].union(
            *(self._attach(invoice, self.env.company) for _ in range(20))
        )
        self.env.invalidate_all()
        Attachment = type(self.env["ir.attachment"])
        original = Attachment._get_stored_content
        reads = []

        def counted(attachment):
            reads.append(attachment)
            return original(attachment)

        with patch.object(Attachment, "_get_stored_content", counted):
            attachments.unlink()
        self.assertFalse(attachments.exists())
        self.assertEqual(reads, [])

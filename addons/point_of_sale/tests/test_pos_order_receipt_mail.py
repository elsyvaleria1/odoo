import base64
import logging
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import PosCashRoundingSessionCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosOrderReceiptAttachments(PosCashRoundingSessionCommon):
    def test_receipt_attachments_are_batched_and_keep_payloads(self):
        order = self._create_bare_order()
        order.account_move = self.env["account.move"].create(
            {"move_type": "out_invoice", "partner_id": self.partner_a.id}
        )
        attachment_model = self.env["ir.attachment"]
        original_create = type(attachment_model).create
        batches = []

        def record_create(records, values):
            batch = values if isinstance(values, list) else [values]
            batches.append(len(batch))
            return original_create(records, values)

        with (
            patch.object(type(attachment_model), "create", record_create),
            patch.object(
                type(self.env["ir.actions.report"]),
                "_render_qweb_pdf",
                return_value=(b"%PDF-audit", "pdf"),
            ) as render,
        ):
            commands = order._create_mail_attachments(
                "Audit", base64.b64encode(b"receipt"), base64.b64encode(b"basic")
            )
        attachments = attachment_model.browse([command[1] for command in commands])
        _logger.debug(
            "Receipt attachment batches=%s records=%s", batches, attachments.ids
        )
        self.assertEqual(batches, [3])
        self.assertEqual(
            attachments.mapped("name"),
            ["Receipt-Audit.jpg", "Receipt-Audit-1.jpg", "Audit.pdf"],
        )
        self.assertEqual(
            [base64.b64decode(item.datas) for item in attachments],
            [b"receipt", b"basic", b"%PDF-audit"],
        )
        self.assertEqual(attachments.mapped("res_model"), ["pos.order"] * 3)
        self.assertEqual(attachments.mapped("res_id"), [order.id] * 3)
        render.assert_called_once_with(
            "account.account_invoices", order.account_move.id
        )

    def test_receipt_without_invoice_or_basic_image_has_one_attachment(self):
        order = self._create_bare_order()
        commands = order._create_mail_attachments(
            "Audit", base64.b64encode(b"receipt"), False
        )
        self.assertEqual(len(commands), 1)
        attachment = self.env["ir.attachment"].browse(commands[0][1])
        self.assertEqual(attachment.res_id, order.id)
        self.assertEqual(base64.b64decode(attachment.datas), b"receipt")

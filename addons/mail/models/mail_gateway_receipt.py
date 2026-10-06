from datetime import timedelta

from odoo import api, fields, models
from odoo.db import claim_row
from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL

_debug = DebugLog(__name__)

RECEIPT_RETENTION = timedelta(days=30)


class MailGatewayReceipt(models.Model):
    _name = "mail.gateway.receipt"
    _description = "Message-Id Received by the Mail Gateway"
    _log_access = False

    message_id = fields.Char(
        string="Message-Id",
        readonly=True,
        required=True,
    )
    receive_date = fields.Datetime(
        string="Received On",
        readonly=True,
        required=True,
    )

    _message_id_uniq = models.Constraint(
        "UNIQUE(message_id)",
        "A Message-Id is received once.",
    )

    @api.model
    def _claim_message_id(self, message_id: str) -> bool:
        cr = self.env.cr
        return claim_row(
            cr,
            lambda: cr.execute(
                SQL(
                    "INSERT INTO mail_gateway_receipt (message_id, receive_date)"
                    " VALUES (%s, %s)",
                    message_id,
                    cr.now(),
                )
            ),
            conflict=f"mail.gateway.receipt {message_id}",
            flush=False,
        )

    @api.model
    def _release_message_id_unless_posted(self, message_id: str) -> None:
        # a message that left nothing behind (a bounce) is processed again when
        # it is delivered again, as it was before receipts existed
        self.env["mail.message"].flush_model(["message_id"])
        self.env.cr.execute(
            SQL(
                "DELETE FROM mail_gateway_receipt WHERE message_id = %s"
                " AND NOT EXISTS (SELECT 1 FROM mail_message WHERE message_id = %s)",
                message_id,
                message_id,
            )
        )
        _debug.logic(
            "receipt_released", message_id=message_id, released=self.env.cr.rowcount
        )

    @api.autovacuum
    def _gc_receipts(self) -> None:
        self.env.cr.execute(
            SQL(
                "DELETE FROM mail_gateway_receipt WHERE receive_date < %s",
                self.env.cr.now() - RECEIPT_RETENTION,
            )
        )
        _debug.lifecycle("receipts_collected", count=self.env.cr.rowcount)

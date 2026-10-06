import uuid
from datetime import timedelta

from odoo.db import db_connect
from odoo.tests.common import TransactionCase, tagged

MAIL = """Return-Path: <receipt.sender@example.com>
From: Receipt Sender <receipt.sender@example.com>
To: nobody@example.com
Subject: {subject}
Message-ID: {msg_id}
Date: Sun, 27 Sep 2026 12:00:00 +0000
Content-Type: text/plain; charset="utf-8"

hello
"""


@tagged("mail_gateway", "post_install", "-at_install")
class TestMailgatewayConcurrentDelivery(TransactionCase):
    def setUp(self):
        super().setUp()
        self.msg_id = f"<receipt-{uuid.uuid4().hex}@example.com>"
        self.mail = MAIL.format(subject=self.msg_id, msg_id=self.msg_id)
        self.addCleanup(self._drop_committed_rows)

    def _drop_committed_rows(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            cr.execute("DELETE FROM mail_test_gateway WHERE name = %s", [self.msg_id])
            cr.execute("DELETE FROM mail_message WHERE message_id = %s", [self.msg_id])
            cr.execute(
                "DELETE FROM mail_gateway_receipt WHERE message_id = %s", [self.msg_id]
            )
            cr.commit()

    def _process(self, cr):
        return self.env(cr=cr)["mixin.mail.thread"].message_process(
            "mail.test.gateway", self.mail
        )

    def test_one_message_delivered_twice_at_once_is_processed_once(self):
        with (
            db_connect(self.env.cr.dbname).cursor() as cr_a,
            db_connect(self.env.cr.dbname).cursor() as cr_b,
        ):
            cr_b.execute("SELECT 1")
            first = self._process(cr_a)
            cr_a.commit()
            second = self._process(cr_b)
            cr_b.commit()
            cr_b.execute(
                "SELECT model, res_id FROM mail_message WHERE message_id = %s",
                [self.msg_id],
            )
            messages = cr_b.fetchall()
        self.assertEqual(
            messages,
            [("mail.test.gateway", first)],
            "the delivery whose snapshot predates the first commit processed it again",
        )
        self.assertFalse(second)

    def test_a_receipt_past_its_retention_is_collected(self):
        Receipt = self.env["mail.gateway.receipt"]
        self.assertTrue(Receipt._claim_message_id(self.msg_id))
        self.assertFalse(Receipt._claim_message_id(self.msg_id))
        self.env.cr.execute(
            "UPDATE mail_gateway_receipt SET receive_date = receive_date - %s"
            " WHERE message_id = %s",
            [timedelta(days=31), self.msg_id],
        )
        Receipt._gc_receipts()
        self.assertTrue(Receipt._claim_message_id(self.msg_id))

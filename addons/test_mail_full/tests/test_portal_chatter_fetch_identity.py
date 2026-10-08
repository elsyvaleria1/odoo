from odoo import Command
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.test_mail_full.tests.test_portal import TestPortal


@tagged("-at_install", "post_install", "portal", "access_link")
class TestPortalChatterFetchIdentity(TestPortal):
    def setUp(self):
        super().setUp()
        self.authenticate(None, None)
        self.own_message, self.other_message = (
            self.env["mail.message"]
            .sudo()
            .create(
                [
                    {
                        "model": self.record_portal._name,
                        "res_id": self.record_portal.id,
                        "message_type": "comment",
                        "subtype_id": self.env.ref("mail.mt_comment").id,
                        "body": f"Written by {author.name}",
                        "author_id": author.id,
                        "attachment_ids": [
                            Command.create(
                                {
                                    "name": f"{author.name}.txt",
                                    "raw": b"attached",
                                    "res_model": self.record_portal._name,
                                    "res_id": self.record_portal.id,
                                }
                            )
                        ],
                    }
                    for author in (self.partner_1, self.partner_2)
                ]
            )
        )

    def _rpc(self, route, credentials):
        return self.url_open(
            route,
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "thread_model": self.record_portal._name,
                    "thread_id": self.record_portal.id,
                    **credentials,
                },
            },
        ).json()

    def _owned(self, credentials):
        reply = self._rpc("/mail/chatter_fetch", credentials)
        self.assertNotIn("error", reply)
        return {
            message["id"]: "ownership_token" in message["attachment_ids"][0]
            for message in reply["result"]["data"]["mail.message"]
            if message["id"] in (self.own_message | self.other_message).ids
        }

    def test_a_signed_hash_alone_reads_the_history_as_its_partner(self):
        credentials = {
            "pid": self.partner_1.id,
            "hash": self.record_portal._sign_token(self.partner_1.id),
        }
        threads = self._rpc("/portal/chatter_init", credentials)["result"]
        self.assertTrue(threads.get("mixin.mail.thread"), "the chatter opens")
        self.assertEqual(
            self._owned(credentials),
            {self.own_message.id: True, self.other_message.id: False},
        )

    def test_a_recipients_link_reads_the_history_as_its_recipient(self):
        token = self.record_portal._portal_get_or_create_token(self.partner_2)
        credentials = {
            "token": token,
            "pid": self.partner_2.id,
            "hash": self.record_portal._sign_token(self.partner_2.id, token=token),
        }
        self.assertEqual(
            self._owned(credentials),
            {self.own_message.id: False, self.other_message.id: True},
        )

    @mute_logger("odoo.http")
    def test_a_forged_hash_reads_nothing(self):
        reply = self._rpc(
            "/mail/chatter_fetch", {"pid": self.partner_1.id, "hash": "0" * 64}
        )
        self.assertIn("error", reply)

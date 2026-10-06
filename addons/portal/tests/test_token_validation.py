from odoo import SUPERUSER_ID
from odoo.tests.common import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.portal.utils import (
    is_thread_hash_pid_valid,
    is_thread_token_valid,
)


class TestTokenValidatorUnit(TransactionCase):
    def test_hash_pid_on_tokenless_thread_returns_false(self):
        partner = self.env.ref("base.partner_root")
        self.assertFalse(is_thread_hash_pid_valid(partner, "deadbeef", partner.id))

    def test_token_on_tokenless_thread_returns_false(self):
        partner = self.env.ref("base.partner_root")
        self.assertFalse(is_thread_token_valid(partner, "some-token"))


class TestDocumentCheckAccess(TransactionCase):
    def test_returns_superuser_uid_recordset(self):
        portal_user = self.env["res.users"].create(
            {
                "name": "doc-check portal",
                "login": "doc_check_portal",
                "password": "doc_check_portal",
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )
        document = self.env(user=portal_user)["access.link"]._open_record(
            "res.partner", portal_user.partner_id.id
        )
        self.assertEqual(document.env.uid, SUPERUSER_ID)


@tagged("-at_install", "post_install")
class TestTokenValidatorHttp(HttpCase):
    @mute_logger("odoo.http")
    def test_chatter_init_hash_pid_tokenless_model_no_500(self):
        result = self.call_jsonrpc(
            "/portal/chatter_init",
            params={
                "thread_model": "res.partner",
                "thread_id": self.env.ref("base.partner_root").id,
                "hash": "deadbeef",
                "pid": 1,
            },
        )
        self.assertIsInstance(result, dict)

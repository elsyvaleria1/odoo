from unittest.mock import patch

from odoo import Command

from .sign_request_common import SignRequestCommon


class TestSignLog(SignRequestCommon):
    def test_sign_request_integrity_depends_on_sign_log_ids(self):
        sign_request = self.create_sign_request_no_item(
            signer=self.partner_1, cc_partners=self.env["res.partner"]
        )
        SignLog = self.env.registry["sign.log"]
        with patch.object(
            SignLog,
            "_get_integrity_error",
            autospec=True,
            side_effect=SignLog._get_integrity_error,
        ) as mocked:
            self.assertTrue(
                sign_request.integrity,
                "A freshly created sign request should have a valid integrity",
            )
            self.assertEqual(mocked.call_count, 1)

            self.env["sign.log"].create(
                {"sign_request_id": sign_request.id, "action": "open"}
            )

            self.assertTrue(sign_request.integrity)
            self.assertEqual(
                mocked.call_count,
                2,
                "integrity must be recomputed once sign_log_ids changes, without needing an unrelated onchange",
            )

    def test_sign_request_create_on_template_without_documents(self):
        empty_template = self.env["sign.template"].create(
            {"name": "template_no_document"}
        )
        sign_request = self.env["sign.request"].create(
            {
                "template_id": empty_template.id,
                "reference": empty_template.display_name,
                "request_item_ids": [
                    Command.create(
                        {
                            "partner_id": self.partner_1.id,
                            "role_id": self.env.ref("sign.sign_item_role_default").id,
                        }
                    )
                ],
            }
        )
        self.assertTrue(sign_request.exists())
        self.assertEqual(
            len(sign_request.sign_log_ids.filtered(lambda log: log.action == "create")),
            1,
        )

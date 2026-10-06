import base64
import hashlib
import json
from hashlib import sha256
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .sign_request_common import SignRequestCommon


@tagged("post_install", "-at_install")
class TestSignIntegrity(SignRequestCommon):
    def _two_document_request(self):
        template = self.env["sign.template"].create({"name": "two documents"})
        for sequence in (1, 2):
            self.env["sign.document"].create(
                {
                    "attachment_id": self.attachment.id,
                    "template_id": template.id,
                    "sequence": sequence,
                }
            )
        return self.env["sign.request"].create(
            {
                "template_id": template.id,
                "reference": template.name,
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

    def _log(self, sign_request, action):
        return sign_request.sign_log_ids.filtered(lambda log: log.action == action)

    def test_creation_fingerprints_every_document(self):
        sign_request = self._two_document_request()
        self.assertEqual(len(self._log(sign_request, "create").digests), 2)
        self.assertTrue(sign_request.integrity)

        sign_request.template_id.document_ids.sorted("sequence")[
            1
        ].attachment_id.sudo().raw = b"%PDF-1.4 tampered"
        sign_request.invalidate_recordset(["integrity", "integrity_error"])

        self.assertFalse(sign_request.integrity)
        self.assertIn("File 2", sign_request.integrity_error)

    def test_completion_fingerprints_the_signed_pdfs(self):
        sign_request = self._two_document_request()
        sign_request.request_item_ids.sudo().sign({})
        self.assertEqual(sign_request.state, "signed")
        completion = self._log(sign_request, "complete")
        self.assertEqual(len(completion.digests), 2)
        self.assertTrue(sign_request.integrity)

        sign_request.completed_document_ids[:1].sudo().file = base64.b64encode(
            b"%PDF-1.4 tampered"
        )
        sign_request.invalidate_recordset(["integrity", "integrity_error"])

        self.assertFalse(sign_request.integrity)
        self.assertIn("Completion", sign_request.integrity_error)

    def test_a_changed_signer_value_breaks_the_chain(self):
        sign_request = self.create_sign_request_1_role(
            self.partner_1, self.env["res.partner"]
        )
        sign_request.request_item_ids.sudo().sign(self.single_signer_sign_values)
        self.assertTrue(sign_request.integrity)

        self.env.cr.execute(
            "UPDATE sign_request_item_value SET value = 'forged' "
            "WHERE sign_request_item_id = %s",
            [sign_request.request_item_ids.id],
        )
        self.env.invalidate_all()

        self.assertFalse(sign_request.integrity)
        self.assertIn("Signature", sign_request.integrity_error)

    def test_entries_hashed_before_versioning_still_verify(self):
        """Version 1 entries, hashed here by an independent copy of the 1.6
        formula, verify under the current code; a forged value still breaks them."""
        sign_request = self.create_sign_request_1_role(
            self.partner_1, self.env["res.partner"]
        )
        item = sign_request.request_item_ids
        item.sudo().sign(self.single_signer_sign_values)
        self.env.flush_all()
        # 1.6 wrote no completion entry; the one 1.7 just wrote would chain to the
        # signature hash rewritten below
        self.env.cr.execute(
            "DELETE FROM sign_log WHERE sign_request_id = %s AND action = 'complete'",
            [sign_request.id],
        )
        self.env.invalidate_all()
        logs = sign_request.sign_log_ids.filtered(
            lambda log: log.action in ("create", "sign")
        ).sorted("id")
        previous = ""
        for log in logs:
            row = {
                key: value[0] if isinstance(value, tuple) else value
                for key, value in log.read()[0].items()
            }
            if log.action == "create":
                body = str(
                    sign_request.template_id.document_ids[0]
                    .with_context(bin_size=False)
                    .attachment_id.datas
                )
            else:
                payload = {
                    field: str(row[field])
                    for field in (
                        "log_date",
                        "action",
                        "partner_id",
                        "request_state",
                        "latitude",
                        "longitude",
                        "ip",
                    )
                }
                for value in item.sign_item_value_ids:
                    payload[str(value.id)] = str(value.value)
                body = json.dumps(
                    payload, sort_keys=True, ensure_ascii=True, indent=None
                )
            log_hash = hashlib.sha256((previous + body).encode("utf-8")).hexdigest()
            self.env.cr.execute(
                "UPDATE sign_log SET hash_version = 1, digests = NULL, log_hash = %s "
                "WHERE id = %s",
                [log_hash, log.id],
            )
            previous = log_hash
        self.env.invalidate_all()
        self.assertTrue(sign_request.integrity, sign_request.integrity_error)

        self.env.cr.execute(
            "UPDATE sign_request_item_value SET value = 'forged' "
            "WHERE sign_request_item_id = %s",
            [item.id],
        )
        self.env.invalidate_all()
        self.assertFalse(sign_request.integrity)

    def test_the_form_view_read_does_not_raise_a_false_alarm(self):
        sign_request = self._two_document_request()
        sign_request.request_item_ids.sudo().sign({})
        self.env.invalidate_all()

        [values] = sign_request.with_context(bin_size=True).web_read(
            {"integrity": {}, "integrity_error": {}}
        )

        self.assertTrue(values["integrity"], values["integrity_error"])

    def test_completed_documents_handed_over_by_a_provider_are_fingerprinted(self):
        sign_request = self._two_document_request()
        provided = b"%PDF-1.4 signed by a provider"
        sign_request.completed_document_ids = self.env[
            "sign.completed.document"
        ].create(
            {
                "sign_request_id": sign_request.id,
                "document_id": sign_request.template_id.document_ids[:1].id,
                "file": base64.b64encode(provided),
            }
        )
        sign_request.request_item_ids.sudo().sign({})

        completion = self._log(sign_request, "complete")
        self.assertEqual(len(completion), 1)
        self.assertEqual(completion.digests, [sha256(provided).hexdigest()])
        self.assertTrue(sign_request.integrity)

    def test_an_entry_s_own_facts_are_bound(self):
        sign_request = self._two_document_request()
        sign_request.request_item_ids.sudo().sign({})
        self.assertTrue(sign_request.integrity)

        self.env.cr.execute(
            "UPDATE sign_log SET ip = '203.0.113.9' WHERE id = %s",
            [self._log(sign_request, "complete").id],
        )
        self.env.invalidate_all()

        self.assertFalse(sign_request.integrity)
        self.assertIn("Completion", sign_request.integrity_error)

    def test_an_anonymous_completion_verifies(self):
        sign_request = self._two_document_request()
        sign_request.request_item_ids.with_user(
            self.env.ref("base.public_user")
        ).sudo().sign({})
        self.assertFalse(self._log(sign_request, "complete").partner_id)
        self.env.invalidate_all()
        self.assertTrue(sign_request.integrity, sign_request.integrity_error)

    def test_merging_a_signer_contact_keeps_the_history_intact(self):
        duplicate = self.env["res.partner"].create(
            {"name": "Signer twin", "email": "signer.twin@example.com"}
        )
        sign_request = self.create_sign_request_1_role(
            duplicate, self.env["res.partner"]
        )
        sign_request.request_item_ids.sudo().sign(self.single_signer_sign_values)
        survivor = self.env["res.partner"].create(
            {"name": "Signer", "email": "signer.twin@example.com"}
        )

        self.env["wizard.res.partner.merge"].create({})._merge(
            [survivor.id, duplicate.id], survivor
        )
        self.env.invalidate_all()

        self.assertEqual(sign_request.request_item_ids.partner_id, survivor)
        self.assertTrue(sign_request.integrity, sign_request.integrity_error)

    def test_the_certificate_is_rendered_after_the_completion_entry(self):
        sign_request = self._two_document_request()
        seen = []
        render = type(self.env["ir.actions.report"])._render_qweb_pdf

        def spy(report, report_ref, res_ids=None, data=None):
            if report_ref == "sign.action_sign_request_print_logs":
                seen.append(bool(self._log(sign_request, "complete")))
            return render(report, report_ref, res_ids, data=data)

        with patch.object(type(self.env["ir.actions.report"]), "_render_qweb_pdf", spy):
            sign_request.request_item_ids.sudo().sign({})

        self.assertEqual(seen[:1], [True])

    def test_a_used_template_s_documents_are_locked(self):
        sign_request = self._two_document_request()
        template = sign_request.template_id
        document = template.document_ids[:1]
        with self.assertRaises(UserError):
            document.sequence = 9
        with self.assertRaises(UserError):
            document.unlink()
        with self.assertRaises(UserError):
            self.env["sign.document"].create(
                {"attachment_id": self.attachment.id, "template_id": template.id}
            )
        with self.assertRaises(UserError):
            template.update_from_attachment_data(
                [{"name": "more.pdf", "datas": self.pdf_data_64}]
            )

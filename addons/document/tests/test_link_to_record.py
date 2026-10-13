from odoo import Command
from odoo.exceptions import AccessError

from odoo.addons.document.tests.test_document_common import TransactionCaseDocuments


class TestLinkToRecord(TransactionCaseDocuments):
    def test_link_to_record_requires_target_write(self):
        doc = self.env["document.document"].create(
            {
                "name": "To link",
                "folder_id": self.folder_a.id,
                "owner_id": self.doc_user.id,
            }
        )
        target = self.env["res.partner"].create({"name": "Link target"})
        self.assertFalse(
            self.env["res.partner"].with_user(self.doc_user).has_access("write")
        )
        wizard = (
            self.env["wizard.document.document.link.record"]
            .with_user(self.doc_user)
            .create(
                {
                    "document_ids": [Command.set(doc.ids)],
                    "resource_ref": f"res.partner,{target.id}",
                }
            )
        )
        with self.assertRaises(AccessError):
            wizard.link_to()

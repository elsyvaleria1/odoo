import base64

from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools.misc import file_open


@tagged("post_install", "-at_install")
class TestOnboardingTour(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # the tour's script, built without demo data: the data folders and the
        # YouTube link ship with the module, the two PDFs and the action do not
        inbox = cls.env.ref("document.document_inbox_folder")
        documents = cls.env["document.document"]
        for name in ("Acme_NDA.pdf", "Mails_inbox.pdf"):
            with file_open(f"document/demo/files/{name}", "rb") as pdf:
                documents.create(
                    {
                        "name": name,
                        "datas": base64.b64encode(pdf.read()),
                        "folder_id": inbox.id,
                        "access_internal": "edit",
                    }
                )
        send_to_finance = cls.env["ir.actions.server"].create(
            {
                "name": "Send to Finance",
                "model_id": cls.env.ref("document.model_document_document").id,
                "usage": "documents_embedded",
                "state": "object_write",
                "update_path": "folder_id",
                "resource_ref": f"document.document,{cls.env.ref('document.document_finance_folder').id}",
            }
        )
        documents.action_folder_embed_action(inbox.id, send_to_finance.id)
        # the demo pins it at install, before a bridge pins its own (expenses,
        # bills): the tour clicks it among the inline actions, not under More
        inbox_actions = cls.env["ir.embedded.actions"].search(
            [
                ("parent_res_model", "=", "document.document"),
                ("parent_res_id", "=", inbox.id),
            ]
        )
        pinned = inbox_actions.filtered(lambda a: a.action_id.id == send_to_finance.id)
        pinned.sequence = min(inbox_actions.mapped("sequence")) - 1

    def test_documents_tour(self):
        self.start_tour("/odoo", "documents_tour", login="admin")

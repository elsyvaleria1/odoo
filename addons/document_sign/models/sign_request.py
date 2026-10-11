from collections import defaultdict
from urllib.parse import urlencode as url_encode

from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SignRequest(models.Model):
    _name = "sign.request"
    _inherit = ["sign.request", "mixin.documents"]

    @api.model_create_multi
    def create(self, vals_list):
        sign_requests = super().create(vals_list)
        attachment_ids = sign_requests.template_id.document_ids.attachment_id.ids
        documents = self.env["document.document"].search(
            [("attachment_id", "in", attachment_ids)]
        )
        attachment_docs = defaultdict(list)
        for doc in documents:
            attachment_docs[doc.attachment_id.id].append(doc)

        for sr in sign_requests:
            if sr.template_id.folder_id and not sr.reference_doc:
                document_ids = []
                for attachment in sr.template_id.document_ids.attachment_id:
                    document_ids += attachment_docs[attachment.id]
                if len(document_ids) == 1:
                    _debug.logic("sign_reference", by="single_document", request=sr)
                    sr.reference_doc = f"document.document,{document_ids[0].id}"
                elif document_ids and all(
                    doc.folder_id == document_ids[0].folder_id for doc in document_ids
                ):
                    _debug.logic("sign_reference", by="common_folder", request=sr)
                    sr.reference_doc = (
                        f"document.document,{document_ids[0].folder_id.id}"
                    )
        return sign_requests

    def _get_linked_record_action(self, default_action=None):
        self.check_singleton()
        if self.reference_doc._name == "document.document":
            url_params = url_encode(
                {
                    "preview_id": self.reference_doc.id,
                    "view_id": self.env.ref("document.document_view_kanban").id,
                    "menu_id": self.env.ref("document.menu_root").id,
                    "folder_id": self.reference_doc.folder_id.id,
                }
            )
            return {
                "type": "ir.actions.act_url",
                "url": f"/odoo/action-document.document_action_preference?{url_params}",
                "target": "self",
            }
        else:
            return super()._get_linked_record_action(default_action=default_action)

    def _create_completed_documents(self) -> None:
        super(
            SignRequest, self.with_context(no_document=False)
        )._create_completed_documents()

    def _send_completed_documents(self) -> None:
        super(
            SignRequest, self.with_context(no_document=True)
        )._send_completed_documents()

    def _get_document_tags(self):
        return self.template_id.documents_tag_ids

    def _get_document_folder(self):
        return self.template_id.folder_id


class SignRequestItem(models.Model):
    _inherit = "sign.request.item"

    def _sign(self, signature, **kwargs):
        super()._sign(signature, **kwargs)
        completed_documents_sudo = self.env["document.document"].search(
            [
                (
                    "attachment_id",
                    "in",
                    self.sign_request_id.completed_document_attachment_ids.ids,
                )
            ]
        )
        partners = self.partner_id | self.create_uid.partner_id
        existing_editors = self.env.ref(
            "base.user_root"
        ).partner_id | partners.filtered(
            lambda partner: all(
                partner in document._member_roles()
                for document in completed_documents_sudo
            )
        )
        if _debug.logic.enabled:
            _debug.logic(
                "signer_access_gate",
                documents=completed_documents_sudo,
                partners=partners,
                already_editors=existing_editors,
            )
        if partners_to_update := partners - existing_editors:
            _debug.lifecycle(
                "signer_access_granted",
                documents=completed_documents_sudo,
                partners=partners_to_update,
            )
            partners = dict.fromkeys(partners_to_update, ("view", False))
            completed_documents_sudo.action_update_access_rights(partners=partners)

        completed_documents_sudo.partner_id = self.partner_id

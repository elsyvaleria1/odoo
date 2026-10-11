from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    @api.ondelete(at_uninstall=False)
    def unlink_except_sign_folder(self) -> None:
        sign_folder = self.env.ref(
            "document_sign.document_sign_folder", raise_if_not_found=False
        )
        if not sign_folder:
            return
        sign_folder_ancestors = set(
            sign_folder.sudo()._get_ancestor_ids(include_self=True)
        )
        if sign_folder_ancestors & set(self.ids):
            _debug.logic("unlink_refused", reason="sign_folder", documents=self)
            raise UserError(
                self.env._(
                    'The "%s" folder is required by the Sign application and cannot be deleted.',
                    sign_folder.name,
                )
            )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_attachment_held_by_sign(self) -> None:
        attachments = self.sudo().attachment_id
        if not attachments:
            return
        held = (
            self.env["sign.document"]
            .sudo()
            .search([("attachment_id", "in", attachments.ids)])
        )
        if held:
            _debug.logic(
                "unlink_refused", reason="held_by_sign_request", documents=self
            )
            raise UserError(
                self.env._(
                    "%s is used by a signature request and cannot be deleted.",
                    held[0].attachment_id.name,
                )
            )

    @api.constrains("company_id")
    def _check_no_company_on_sign_folder(self) -> None:
        if not self.company_id:
            return
        if (
            (
                sign_folder := self.env.ref(
                    "document_sign.document_sign_folder", raise_if_not_found=False
                )
            )
            and sign_folder in self
            and sign_folder.company_id
        ):
            _debug.logic("company_refused", reason="sign_folder")
            raise UserError(
                self.env._(
                    "You cannot set a company on the %s folder.", sign_folder.name
                )
            )

    @api.constrains("active")
    def _check_sign_folder_active(self) -> None:
        if all(d.active for d in self):
            return
        sign_folder = self.env.ref(
            "document_sign.document_sign_folder", raise_if_not_found=False
        )
        if sign_folder and sign_folder in self and not sign_folder.active:
            _debug.logic("archive_refused", reason="sign_folder")
            raise UserError(
                self.env._("You cannot archive the Sign folder (%s).", sign_folder.name)
            )

    def document_sign_create_sign_template(self, folder_id=False):
        if self.filtered(
            lambda doc: (
                doc.type != "binary"
                or doc.shortcut_document_id
                or not doc.mimetype
                or "pdf" not in doc.mimetype.lower()
            )
        ):
            _debug.logic("sign_template_refused", reason="not_pdf", documents=self)
            raise UserError(
                self.env._("This action can only be applied on pdf document.")
            )

        create_values = {
            "favorite_user_ids": [Command.link(self.env.user.id)],
            "folder_id": folder_id or self[0].folder_id.id,
        }

        all_tags = self.tag_ids
        if all_tags:
            create_values["documents_tag_ids"] = [Command.set(all_tags.ids)]

        template = self.env["sign.template"].create(create_values)
        self.env["sign.document"].create(
            [
                {
                    "attachment_id": doc.attachment_id.id,
                    "template_id": template.id,
                }
                for doc in self
            ]
        )

        _debug.lifecycle("sign_template_created", documents=self, template=template)
        return template.go_to_custom_template(sign_directly_without_mail=True)

    def _get_domain_gc_clear_bin(self):
        return Domain.AND(
            [
                super()._get_domain_gc_clear_bin(),
                [("res_model", "!=", "sign.request")],
                [("res_model", "!=", "sign.document")],
            ]
        )

    @api.model
    def _data_embed_sign_create_sign_template_direct(self) -> None:
        action_sign = self.env.ref(
            "document_sign.ir_actions_server_create_sign_template_direct"
        )
        if internal_folder := self.env.ref(
            "document.document_internal_folder", raise_if_not_found=False
        ):
            self.action_folder_embed_action(internal_folder.id, action_sign.id)
        if inbox_folder := self.env.ref(
            "document.document_inbox_folder", raise_if_not_found=False
        ):
            self.action_folder_embed_action(inbox_folder.id, action_sign.id)

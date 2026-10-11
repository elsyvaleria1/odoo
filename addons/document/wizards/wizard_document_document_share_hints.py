from odoo import api, models
from odoo.fields import Domain


class WizardDocumentDocumentShare(models.TransientModel):
    _inherit = "wizard.document.document.share"


    @api.depends("access_internal", "document_ids")
    def _compute_access_internal_help(self) -> None:
        for record in self:
            if record.access_internal.endswith("view"):
                if record.is_folder_only:
                    record.access_internal_help = self.env._(
                        "Can only view contents. Cannot add, modify, or delete items."
                    )
                else:
                    record.access_internal_help = self.env._(
                        "Can only view. Cannot rename, move, or delete."
                    )
            elif record.access_internal.endswith("edit"):
                if record.is_folder_only:
                    record.access_internal_help = self.env._(
                        "Can add, modify, and delete files within this folder."
                    )
                else:
                    record.access_internal_help = self.env._(
                        "Can modify, delete, and rename."
                    )
            elif record.access_internal == "mixed":
                record.access_internal_help = self.env._(
                    "Keep the values as is (multiple values)"
                )
            else:
                record.access_internal_help = self.env._(
                    "Only people with access can open with the link"
                )

    @api.depends("access_via_link", "document_ids")
    def _compute_access_via_link_help(self) -> None:
        for record in self:
            if record.access_via_link.endswith("view"):
                if record.is_folder_only:
                    record.access_via_link_help = self.env._(
                        "Can only view contents. Cannot add, modify, or delete items."
                    )
                else:
                    record.access_via_link_help = self.env._(
                        "Can only view. Cannot rename, move, or delete."
                    )
            elif record.access_via_link.endswith("edit"):
                if record.is_folder_only:
                    record.access_via_link_help = self.env._(
                        "Can add, modify, and delete files within this folder."
                    )
                else:
                    record.access_via_link_help = self.env._(
                        "Can modify, delete, and rename."
                    )
            elif record.access_via_link == "mixed":
                record.access_via_link_help = self.env._(
                    "Keep the values as is (multiple values)"
                )
            else:
                record.access_via_link_help = self.env._(
                    "No one on the internet can access"
                )

    @api.depends(
        "access_internal",
        "access_via_link",
        "share_access_ids.role",
        "invite_partner_ids",
    )
    def _compute_has_warning_link_with_more_rights(self) -> None:
        for record in self:
            record.has_warning_link_with_more_rights = (
                not record.invite_partner_ids
                and record.access_via_link.endswith("edit")
                and (
                    record.access_internal.endswith("view")
                    or any(
                        a.role.endswith("view")
                        for a in record.share_access_ids
                        if not a.is_deleted
                    )
                )
            )

    @api.depends(
        "access_via_link",
        "invite_partner_ids",
        "share_access_ids.partner_id.user_ids",
        "share_access_ids.is_deleted",
    )
    def _compute_has_warning_partners_without_access(self) -> None:
        for record in self:
            record.has_warning_partners_without_access = any(
                r.has_warning_no_access for r in record.share_access_ids
            )

    @api.depends_context("uid")
    @api.depends(
        "access_internal",
        "access_via_link",
        "share_access_ids.role",
        "share_access_ids.is_deleted",
        "share_access_ids.partner_id",
        "invite_partner_ids",
        "document_ids",
    )
    def _compute_has_warning_self_access_loss(self) -> None:
        me = self.env.user.partner_id
        Documents = self.env["document.document"]
        system_reach = Documents._documents_system_reach()
        system_reached = (
            set(
                Documents.search(
                    Domain("id", "in", self.document_ids.ids) & system_reach
                ).ids
            )
            if self.document_ids and not system_reach.is_false()
            else set()
        )
        for record in self:
            keeps_via_owner = record.document_ids and all(
                document.owner_id == self.env.user for document in record.document_ids
            )
            keeps_via_system = (
                bool(record.document_ids)
                and set(record.document_ids.ids) <= system_reached
            )
            if record.invite_partner_ids or keeps_via_system or keeps_via_owner:
                record.has_warning_self_access_loss = False
                continue
            keeps_membership = any(
                access.partner_id == me
                and not access.is_deleted
                and not access.role.endswith("none")
                for access in record.share_access_ids
            )
            keeps_via_internal = (
                not self.env.user.share and not record.access_internal.endswith("none")
            )
            keeps_via_link = not record.access_via_link.endswith("none")
            record.has_warning_self_access_loss = not (
                keeps_membership or keeps_via_internal or keeps_via_link
            )

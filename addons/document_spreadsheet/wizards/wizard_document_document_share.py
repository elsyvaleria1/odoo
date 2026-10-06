from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardDocumentDocumentShare(models.TransientModel):
    _inherit = "wizard.document.document.share"

    error_message_spreadsheet = fields.Char(
        string="Error Message",
        compute="_compute_error_message_spreadsheet",
    )

    @api.depends(
        "document_ids",
        "invite_partner_ids",
        "invite_role",
        "share_access_ids.role",
        "access_internal",
        "access_via_link",
    )
    def _compute_error_message_spreadsheet(self) -> None:
        for wizard in self:
            wizard.error_message_spreadsheet = False
            sp_frozen_docs = wizard.document_ids.filtered(
                lambda d: d.handler == "frozen_spreadsheet"
            )
            sp_non_frozen_docs = wizard.document_ids.filtered(
                lambda d: d.handler == "spreadsheet"
            )
            sp_docs = sp_frozen_docs | sp_non_frozen_docs

            error_partners = self.env["res.partner"]
            is_inviting = wizard.invite_partner_ids
            edit_access_partner = wizard.share_access_ids.filtered(
                lambda s: s.role.endswith("edit")
            ).partner_id
            has_edit = (
                wizard.invite_role == "edit"
                if is_inviting
                else (
                    wizard.access_internal.endswith("edit")
                    or wizard.access_via_link.endswith("edit")
                    or edit_access_partner
                )
            )
            if has_edit and sp_frozen_docs:
                wizard.error_message_spreadsheet = self.env._(
                    "Read only spreadsheet(s): %(document_names)s.",
                    document_names=", ".join(
                        sp_frozen_docs.sorted("display_name").mapped("display_name")
                    ),
                )
                error_partners = edit_access_partner
            elif sp_docs and wizard.access_via_link.endswith("edit"):
                wizard.error_message_spreadsheet = self.env._(
                    "You cannot share spreadsheet(s) via link in edit mode (%(document_names)s).",
                    document_names=", ".join(
                        sp_docs.sorted("display_name").mapped("display_name")
                    ),
                )
            elif sp_docs and (
                edit_partner_share := (
                    wizard.invite_partner_ids
                    if is_inviting and wizard.invite_role == "edit"
                    else wizard.share_access_ids.filtered(
                        lambda s: s.role.endswith("edit")
                    ).partner_id
                ).filtered(lambda p: p.partner_share)
            ):
                wizard.error_message_spreadsheet = self.env._(
                    "You can not share spreadsheet(s) in edit mode (%(document_names)s) to non-internal users.",
                    document_names=", ".join(
                        sp_docs.sorted("display_name").mapped("display_name")
                    ),
                )
                error_partners = edit_partner_share

            _debug.logic(
                "spreadsheet_sharing_checked",
                wizard=wizard,
                spreadsheets=len(sp_docs),
                frozen=len(sp_frozen_docs),
                blocked=bool(wizard.error_message_spreadsheet),
                partners_flagged=len(error_partners),
            )
            if wizard.error_message_spreadsheet and error_partners:
                wizard.error_message_spreadsheet += " "
                wizard.error_message_spreadsheet += self.env._(
                    "Partner(s): %(partner_names)s.",
                    partner_names=", ".join(
                        error_partners.sorted("display_name").mapped("display_name")
                    ),
                )

    def _compute_access_internal_help(self) -> None:
        super()._compute_access_internal_help()
        for record in self:
            if all(
                d.handler in ("spreadsheet", "frozen_spreadsheet")
                for d in record.document_ids
            ):
                if record.access_internal.endswith("view"):
                    record.access_internal_help = self.env._(
                        "Can view the spreadsheet. Cannot make changes."
                    )
                elif record.access_internal.endswith("edit"):
                    record.access_internal_help = self.env._(
                        "Can edit the spreadsheet, including structure and content."
                    )

    def _compute_access_via_link_help(self) -> None:
        super()._compute_access_via_link_help()
        for record in self:
            is_spreadsheet_only = all(
                d.handler in ("spreadsheet", "frozen_spreadsheet")
                for d in record.document_ids
            )
            if is_spreadsheet_only and record.access_via_link.endswith("view"):
                record.access_via_link_help = self.env._(
                    "Can view the spreadsheet. Cannot make changes."
                )

    @api.depends("error_message_spreadsheet")
    def _compute_has_warning_link_with_more_rights(self) -> None:
        """Hide other errors if we show the spreadsheet errors."""
        with_spreadsheet_errors = self.filtered("error_message_spreadsheet")
        with_spreadsheet_errors.has_warning_link_with_more_rights = False
        super(
            WizardDocumentDocumentShare, self - with_spreadsheet_errors
        )._compute_has_warning_link_with_more_rights()

    @api.depends("error_message_spreadsheet")
    def _compute_has_warning_partners_without_access(self) -> None:
        """Hide other errors if we show the spreadsheet errors."""
        with_spreadsheet_errors = self.filtered("error_message_spreadsheet")
        with_spreadsheet_errors.has_warning_partners_without_access = False
        super(
            WizardDocumentDocumentShare, self - with_spreadsheet_errors
        )._compute_has_warning_partners_without_access()

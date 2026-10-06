from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsAccess(models.Model):
    _inherit = "document.access"

    @api.constrains("document_id", "partner_id", "role")
    def _check_spreadsheet(self) -> None:
        """Check that only internal user can edit a spreadsheet."""
        for access in self:
            user_ids = access.partner_id.with_context(active_test=False).user_ids
            if (
                access.document_id.handler == "spreadsheet"
                and access.partner_id
                and (not user_ids or all(user_ids.mapped("share")))
                and access.role in ("edit", "manage")
            ):
                _debug.logic(
                    "spreadsheet_access_rejected",
                    access=access,
                    reason="edit_for_non_internal",
                )
                raise ValidationError(
                    self.env._(
                        "Spreadsheets can not be shared in edit mode to non-internal users."
                    )
                )

            if access.document_id.handler == "frozen_spreadsheet" and access.role in (
                "edit",
                "manage",
            ):
                _debug.logic(
                    "spreadsheet_access_rejected", access=access, reason="edit_frozen"
                )
                raise ValidationError(
                    self.env._("Frozen Spreadsheets can not be editable.")
                )

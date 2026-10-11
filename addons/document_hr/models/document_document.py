from odoo import models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    def write(self, vals):
        self._check_employee_roots_stay_closed(vals)
        return super().write(vals)

    def _update_access_rights(
        self,
        access_internal=None,
        access_via_link=None,
        is_access_via_link_hidden=None,
        partners=None,
        no_propagation=False,
        is_download_blocked=None,
        is_access_restricted=None,
    ):
        self._check_employee_roots_stay_closed(
            {
                key: value
                for key, value in (
                    ("access_internal", access_internal),
                    ("access_via_link", access_via_link),
                    ("is_access_restricted", is_access_restricted),
                )
                if value is not None
            }
        )
        return super()._update_access_rights(
            access_internal=access_internal,
            access_via_link=access_via_link,
            is_access_via_link_hidden=is_access_via_link_hidden,
            partners=partners,
            no_propagation=no_propagation,
            is_download_blocked=is_download_blocked,
            is_access_restricted=is_access_restricted,
        )

    def _check_employee_roots_stay_closed(self, vals) -> None:
        opening = (
            vals.get("access_internal", "none") != "none"
            or vals.get("access_via_link", "none") != "none"
            or vals.get("is_access_restricted", True) is False
        )
        if not opening or not self.ids:
            return
        roots = (
            self.env["res.company"]
            .with_context(active_test=False)
            .search([("documents_employee_folder_id", "in", self.ids)])
            .documents_employee_folder_id
        )
        if roots:
            _debug.logic("employee_root_open_refused", folders=roots)
            raise ValidationError(
                self.env._(
                    "The employees folder “%s” stays closed: share the employee "
                    "folders or documents inside it instead.",
                    roots[0].name,
                )
            )

    def _get_unauthorized_root_document_owners_sudo(self):
        unauthorized_owners_sudo = super()._get_unauthorized_root_document_owners_sudo()
        return unauthorized_owners_sudo.with_context(active_test=False).filtered(
            lambda u: not u.employee_id
        )

    def _raise_if_used_folder(self):
        if folder_ids := self.filtered(lambda d: d.type == "folder").ids:
            employees_folders_in_self = (
                self.env["hr.employee"]
                .sudo()
                .search_count(
                    [
                        "|",
                        ("hr_employee_folder_id", "child_of", folder_ids),
                        ("hr_employee_contract_folder_id", "child_of", folder_ids),
                    ],
                    limit=1,
                )
            )
            if employees_folders_in_self:
                _debug.logic(
                    "unlink_refused", reason="employee_folder", folders=folder_ids
                )
                raise ValidationError(
                    self.env._(
                        "Impossible to delete employee folder or employee 'Contract' folder"
                    )
                )
        return super()._raise_if_used_folder()

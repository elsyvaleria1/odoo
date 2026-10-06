from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrLeave(models.Model):
    _name = "hr.leave"
    _inherit = ["hr.leave", "mixin.documents"]

    def _get_document_folder(self):
        # the employee's own folder, beside their other files; the employees
        # root only for one not provisioned yet
        folder = (
            self.employee_id.hr_employee_folder_id
            or self.employee_id.company_id.documents_employee_folder_id
        )
        _debug.logic("leave_document_folder", leave=self, folder=folder)
        return folder

    def _get_document_access_ids(self):
        return [(self.employee_id.partner_id, ("view", False))]

    def _check_create_documents(self):
        return (
            self.employee_id.company_id.documents_hr_settings
            and super()._check_create_documents()
        )

    def _get_document_partner(self):
        return self.employee_id.partner_id

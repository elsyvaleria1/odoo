from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrVersion(models.Model):
    _name = "hr.version"
    _inherit = ["hr.version", "mixin.documents"]

    def _get_document_access_ids(self):
        return [(self.employee_id.partner_id, ("view", False))]

    def _get_document_tags(self):
        return self.company_id.documents_hr_contracts_tags

    def _get_document_partner(self):
        return self.employee_id.partner_id

    def _get_document_folder(self):
        employee = self.employee_id
        folder = (
            employee.hr_employee_contract_folder_id
            or employee.hr_employee_folder_id
            or self.company_id.documents_employee_folder_id
        )
        _debug.logic("version_document_folder", version=self, folder=folder)
        return folder

    def _check_create_documents(self):
        return (
            self.company_id.documents_hr_settings and super()._check_create_documents()
        )

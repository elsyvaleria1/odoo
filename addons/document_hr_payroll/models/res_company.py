from odoo import Command, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    documents_hr_payslips_tags = fields.Many2many(
        comodel_name="document.tag",
        relation="payslip_tags_table",
    )

    worker_payroll_folder_id = fields.Many2one(
        comodel_name="document.document",
        domain=[("type", "=", "folder"), ("shortcut_document_id", "=", False)],
        check_company=True,
        help="Folder used when an employee with no user exists in the company, "
        "to store their payroll documents in a centralized place.",
    )

    def _generate_employee_documents_main_folders(self):
        folders = super()._generate_employee_documents_main_folders()
        self._apply_payslip_documents_settings()
        return folders

    def write(self, vals):
        result = super().write(vals)
        if vals.get("documents_employee_folder_id"):
            self._apply_payslip_documents_settings()
        return result

    def _apply_payslip_documents_settings(self) -> None:
        payslip_tag = self.env.ref(
            "document_hr_payroll.documents_tag_payslips", raise_if_not_found=False
        )
        if payslip_tag:
            self.sudo().filtered(lambda c: not c.documents_hr_payslips_tags).write(
                {"documents_hr_payslips_tags": [Command.set(payslip_tag.ids)]}
            )
        group_payroll_user = self.env.ref("hr_payroll.group_hr_payroll_user")
        Access = self.env["document.access"]
        for company in self:
            root = company.documents_employee_folder_id
            _debug.lifecycle("payroll_folder_access", company=company, folder=root)
            Access._sync_caused_grants(
                f"res.company,{company.id}",
                [(root.id, "group_id", group_payroll_user.id, "edit", company.id)]
                if root
                else [],
            )

    def _get_domain_used_folder_ids(self, folder_ids):
        return super()._get_domain_used_folder_ids(folder_ids) | Domain(
            "worker_payroll_folder_id", "in", folder_ids
        )

    def _get_or_create_worker_payroll_folder(self):
        self.check_singleton()
        if not self.worker_payroll_folder_id:
            _debug.lifecycle("worker_payroll_folder_created", company=self)
            self.sudo().worker_payroll_folder_id = (
                self.env["document.document"]
                .sudo()
                .create(
                    {
                        "name": self.env._("Payroll %s", self.name),
                        "type": "folder",
                        "owner_id": False,
                        "folder_id": self.documents_employee_folder_id.id,
                    }
                )
                .id
            )
        return self.sudo().worker_payroll_folder_id

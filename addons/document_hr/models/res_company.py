from odoo import Command, api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    documents_hr_settings = fields.Boolean(default=True)
    documents_employee_folder_id = fields.Many2one(
        comodel_name="document.document",
        string="Employees Folder",
        domain=[("type", "=", "folder"), ("shortcut_document_id", "=", False)],
        check_company=True,
    )
    employee_subfolders = fields.Char(
        string="Employees Subfolder",
        help="Comma separated list of folder names that need to be created under each employee folder.",
    )
    documents_hr_contracts_tags = fields.Many2many(
        comodel_name="document.tag",
        relation="documents_hr_contracts_tags_table",
    )

    def _get_domain_used_folder_ids(self, folder_ids):
        return super()._get_domain_used_folder_ids(folder_ids) | (
            Domain("documents_employee_folder_id", "in", folder_ids)
            & Domain("documents_hr_settings", "=", True)
        )

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._generate_employee_documents_main_folders()
        return companies

    def write(self, vals):
        """Override to move all employee subfolders if the HR Employee folder has been modified in settings.
        And ensure that companies that were never configured get their employee subfolders."""
        subfolders_changed = "employee_subfolders" in vals
        employees_without_subfolder = self.env["hr.employee"]
        employees_with_subfolders = self.env["hr.employee"]
        if vals.get("documents_employee_folder_id"):
            # active_test=False: an archived employee's folder must move with
            # the others, or it stays under a root no company references any
            # more and its documents drop out of the configured tree.
            employees = (
                self.env["hr.employee"]
                .sudo()
                .with_context(active_test=False)
                .search([("company_id", "in", self.ids)])
            )
            # Some companies may never have been configured, so no subfolder exists for their employees.
            employees_without_subfolder = employees.filtered(
                lambda e: not e.hr_employee_folder_id
            )
            employees_with_subfolders = employees - employees_without_subfolder
            _debug.pipeline(
                "employee_root_moved",
                companies=self,
                moved=len(employees_with_subfolders),
                unprovisioned=len(employees_without_subfolder),
            )
            employees_with_subfolders.hr_employee_folder_id.folder_id = vals[
                "documents_employee_folder_id"
            ]
            # done in two steps, otherwise folder_id would propagate its own access rights instead of the written values
            employees_with_subfolders.hr_employee_folder_id.write(
                {
                    "access_via_link": "none",
                    "access_internal": "none",
                }
            )
        result = super().write(vals)
        if vals.get("documents_employee_folder_id"):
            self._secure_employee_roots()
        if employees_without_subfolder:
            employees_without_subfolder._create_employee_documents_folders(
                skip_subfolders=subfolders_changed
            )
        if subfolders_changed:
            _debug.pipeline("employee_subfolders_resynced", companies=self)
            self.env["hr.employee"].with_context(active_test=False).search(
                [("company_id", "in", self.ids)]
            )._create_employee_documents_subfolders()
        return result

    def _generate_employee_documents_main_folders(self):
        # Only companies that have no root folder yet: overwriting the pointer
        # would orphan the previous root and every employee folder under it.
        # The return value still covers all of self, so overrides that zip it
        # against self (documents_hr_payroll) stay aligned.
        _debug.pipeline("employee_roots_provision", companies=self)
        for company in self.filtered(lambda c: not c.documents_employee_folder_id):
            company.sudo().documents_employee_folder_id = (
                self.env["document.document"]
                .sudo()
                .create(
                    {
                        "name": company.env._("Employees - %s", company.name),
                        "type": "folder",
                        "folder_id": False,
                        "company_id": company.id,
                        "access_internal": "none",
                        "access_via_link": "none",
                        "is_access_via_link_hidden": True,
                        "is_access_restricted": True,
                    }
                )
            )
        # Every company needs its contracts tagged, not only base.main_company
        # (round-2 audit R2: the old noupdate data record that hardcoded that
        # one company was redundant with this loop and has been removed).
        # Same place documents_hr_payroll assigns its own payslip tags.
        contracts_tag = self.env.ref(
            "document_hr.documents_hr_tag_contracts", raise_if_not_found=False
        )
        if contracts_tag:
            for company in self.filtered(lambda c: not c.documents_hr_contracts_tags):
                company.sudo().documents_hr_contracts_tags = [
                    Command.set(contracts_tag.ids)
                ]
        return self.mapped("documents_employee_folder_id")

    def _secure_employee_roots(self) -> None:
        # a boundary closed to the company and to any link: what grants reach
        # it (HR's, payroll's) flow on to every employee folder beneath, and
        # nothing above it -- the folder an admin re-pointed it under
        # included -- reaches in
        roots = self.documents_employee_folder_id.sudo().filtered(
            lambda root: (
                root.access_internal != "none"
                or root.access_via_link != "none"
                or not root.is_access_restricted
            )
        )
        if roots:
            _debug.lifecycle("employee_roots_secured", folders=roots)
            roots.action_update_access_rights(
                access_internal="none",
                access_via_link="none",
                is_access_via_link_hidden=True,
                is_access_restricted=True,
                no_propagation=True,
            )

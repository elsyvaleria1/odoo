from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrEmployee(models.Model):
    _name = "hr.employee"
    _inherit = ["hr.employee", "mixin.documents"]

    document_count = fields.Integer(
        compute="_compute_document_count",
        compute_sudo=True,
    )
    partner_document_count = fields.Integer(
        related="partner_id.document_count",
        string="Contact Document Count",
    )
    hr_employee_folder_id = fields.Many2one(
        comodel_name="document.document",
        string="HR Employee Folder",
        groups="base.group_system,hr.group_hr_user",
    )
    hr_employee_contract_folder_id = fields.Many2one(
        comodel_name="document.document",
        string="HR Employee Contract Folder",
        groups="base.group_system,hr.group_hr_user",
    )

    def _get_document_folder(self):
        return (
            self.hr_employee_folder_id
            if self.company_id.documents_hr_settings
            else False
        )

    def _get_document_partner(self):
        return self.partner_id

    def _check_create_documents(self):
        return (
            self.company_id.documents_hr_settings and super()._check_create_documents()
        )

    @api.depends("hr_employee_folder_id", "partner_id")
    def _compute_document_count(self) -> None:
        # Branch per record, not on the batch: `self.hr_employee_folder_id` is
        # the union over every record being computed, so a mixed batch used to
        # take the folder path for everyone and silently return 0 for the
        # folder-less ones instead of their partner-based count.
        with_folder = self.filtered("hr_employee_folder_id")
        _debug.logic(
            "employee_document_count",
            employees=self,
            by_folder=len(with_folder),
            by_partner=len(self) - len(with_folder),
        )

        # Transitional: only while the documents-hr setting is optional; drop this branch once it is mandatory.
        if without_folder := self - with_folder:
            # Search everywhere if no employee folder configured.
            document_count_by_partner = dict(
                self.env["document.document"]._read_group(
                    [("partner_id", "in", without_folder.partner_id.ids)],
                    groupby=["partner_id"],
                    aggregates=["__count"],
                )
            )
            for employee in without_folder:
                employee.document_count = document_count_by_partner.get(
                    employee.partner_id, 0
                )

        if not with_folder:
            return
        document_count_by_folder = dict(
            self.env["document.document"]._read_group(
                [
                    ("id", "child_of", with_folder.hr_employee_folder_id.ids),
                    ("type", "!=", "folder"),
                ],
                groupby=["folder_id"],
                aggregates=["__count"],
            )
        )

        document_count_by_employee_folder = {
            folder: sum(
                count
                for doc_folder, count in document_count_by_folder.items()
                if doc_folder._is_descendant_of(folder)
            )
            for folder in with_folder.hr_employee_folder_id
        }
        for employee in with_folder:
            employee.document_count = document_count_by_employee_folder.get(
                employee.hr_employee_folder_id, 0
            )

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        if not self.env.context.get("salary_simulation", False):
            employees._create_employee_documents_folders()
        return employees

    def write(self, vals):
        result = super().write(vals)
        if "name" in vals and len(self) == 1:
            _debug.lifecycle("employee_folder_renamed", employee=self)
            # This makes no sense to rename multiple employees with the same name. This would probably be an error.
            # So we rename the folder only if one employee is renamed at a time.
            self.sudo().hr_employee_folder_id.write({"name": vals["name"]})
        return result

    def action_see_documents(self):
        # The person's own documents, reached from their own profile.
        self.check_singleton()
        if self.is_user:
            return self.partner_id.action_see_documents()
        return None

    def action_view_documents(self):
        """Open and display all the content of the employee subfolder under HR > Employee."""
        self.check_singleton()
        # Gate both branches below the same way: neither the "search
        # everywhere" fallback nor the folder-based act_url is meant to be
        # reachable by a user outside HR, regardless of document_hr_settings.
        if not self.env.user.has_groups("hr.group_hr_user"):
            _debug.logic("employee_folder_refused", reason="not_hr_user", employee=self)
            raise AccessError(self.env._("You cannot access the employee's folder."))
        # If setting not activated, use the old filter -> Search everywhere
        if not self.company_id.documents_hr_settings:
            _debug.logic("employee_documents", by="search_everywhere", employee=self)
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "document.document_action_preference"
            )
            action["context"] = {
                "default_partner_id": self.partner_id.id,
                "searchpanel_default_folder_id": False,
                "default_res_id": self.id,
                "default_res_model": "hr.employee",
            }
            return action
        if not self.hr_employee_folder_id:
            _debug.logic(
                "employee_folder_refused", reason="unconfigured", employee=self
            )
            raise ValidationError(
                self.env._(
                    "You must configure the HR Employee folder in document settings to use Document's features."
                )
            )
        return {
            "type": "ir.actions.act_url",
            "url": self.hr_employee_folder_id.sudo().access_url,
        }

    def _create_employee_documents_folders(self, skip_subfolders=False) -> None:
        """Employee document folder is meant to be used by HR only to store all the documents they need regarding the
        employee (E.g.: ID Card, Drive License, etc..). The employee does not have access to this folder,
        nor the documents inside it (by default at least)"""
        # Deliberately not gated on company_id.documents_hr_settings, unlike
        # every other decision point in this module: nothing back-fills folders
        # when the switch is turned back on (res.company.write back-fills on
        # documents_employee_folder_id changing, not on the switch), so
        # skipping provisioning while it is off would leave every employee
        # hired in between permanently folder-less. Provision always, and gate
        # only the filing. Changing that needs the back-fill written first.
        employees = self.filtered("company_id.documents_employee_folder_id")
        # Never hand a second folder to an employee that already has one:
        # overwriting the pointer orphans the old folder and its documents.
        # Subfolder generation below still covers all of `employees`.
        employees_without_folder = employees.filtered(
            lambda e: not e.hr_employee_folder_id
        )
        _debug.pipeline(
            "employee_folders_provision",
            employees=employees,
            missing=len(employees_without_folder),
            skip_subfolders=skip_subfolders,
        )
        folders = (
            self.env["document.document"]
            .sudo()
            .create(
                [
                    {
                        "name": employee.name,
                        "type": "folder",
                        "folder_id": employee.company_id.documents_employee_folder_id.id,
                        "company_id": employee.company_id.id,
                        "access_internal": "none",
                        "access_via_link": "none",
                        "is_access_via_link_hidden": True,
                        "owner_id": False,
                    }
                    for employee in employees_without_folder
                ]
            )
        )
        for employee, folder in zip(employees_without_folder, folders, strict=False):
            employee.hr_employee_folder_id = folder.id
            # create Contracts Subfolder
            if not employee.hr_employee_contract_folder_id:
                employee.hr_employee_contract_folder_id = (
                    self.env["document.document"]
                    .sudo()
                    .create(
                        [
                            {
                                "name": self.env._("Contracts"),
                                "type": "folder",
                                "folder_id": employee.hr_employee_folder_id.id,
                                "company_id": employee.company_id.id,
                            }
                        ]
                    )
                )
        if not skip_subfolders:
            employees._create_employee_documents_subfolders()

    def _create_employee_documents_subfolders(self) -> None:
        """Generate subfolders under the employee folder, following what is specified on the company
        -> res_config_settings.employee_subfolders
        Removing a folder name from the setting should not delete the folder if it's not empty.
        Existing folders should not be recreated.
        Only newly added folder name should generate a new subfolder.
        """
        Documents = self.env["document.document"]
        create_subfolders_vals = []
        subfolders_to_delete = Documents

        subfolders = Documents.search(
            [
                ("type", "=", "folder"),
                ("folder_id", "in", self.hr_employee_folder_id.ids),
                ("id", "not in", self.hr_employee_contract_folder_id.ids),
            ]
        )
        subfolders_by_employee_folder = subfolders.grouped("folder_id")
        for company, company_employees in self.grouped("company_id").items():
            # Strip here, once: the names are compared against the stored
            # folder names below, so stripping only at creation time made
            # " Beta" look missing and "Beta" look removed on every save.
            subfolder_names = [
                stripped
                for name in (company.employee_subfolders or "").split(",")
                if (stripped := name.strip())
            ]
            for employee in company_employees.filtered("hr_employee_folder_id"):
                # Add new folders added to the list
                existing_subfolders = subfolders_by_employee_folder.get(
                    employee.hr_employee_folder_id, Documents
                )
                added_subfolder_names = list(
                    set(subfolder_names) - set(existing_subfolders.mapped("name"))
                )
                create_subfolders_vals.extend(
                    {
                        "name": subfolder_name,
                        "type": "folder",
                        "folder_id": employee.hr_employee_folder_id.id,
                        "company_id": company.id,
                    }
                    for subfolder_name in added_subfolder_names
                )

                # Delete removed folder from the list.
                # -> Side effect : folders created manually that are still empty will be deleted.
                removed_subfolders_names = list(
                    set(existing_subfolders.mapped("name")) - set(subfolder_names)
                )
                subfolders_to_delete |= existing_subfolders.filtered_domain(
                    [("name", "in", removed_subfolders_names)]
                ).filtered(lambda f: not f.children_ids)
        _debug.pipeline(
            "employee_subfolders",
            employees=self,
            created=len(create_subfolders_vals),
            deleted=len(subfolders_to_delete),
        )
        if create_subfolders_vals:
            self.env["document.document"].sudo().create(create_subfolders_vals)
        subfolders_to_delete.unlink()

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    # for folders
    project_ids = fields.One2many(
        comodel_name="project.project",
        inverse_name="documents_folder_id",
        string="Projects",
    )

    def _prepare_create_values(self, vals_list):
        vals_list = super()._prepare_create_values(vals_list)
        folder_ids = {
            folder_id
            for v in vals_list
            if (folder_id := v.get("folder_id")) and not v.get("res_id")
        }
        folder_id_values = {
            folder_id: self.browse(folder_id)._prepare_link_to_project_vals()
            for folder_id in folder_ids
        }
        for vals in vals_list:
            if (
                (folder_id := vals.get("folder_id"))
                and vals.get("type") != "folder"
                and not vals.get("res_id")
            ):
                _debug.logic("project_link_inherited", folder=folder_id)
                vals.update(
                    {
                        k: v
                        for k, v in folder_id_values[folder_id].items()
                        if k not in vals
                    }
                )
        return vals_list

    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        domain = domain.optimize(self)
        if (
            template_folder_id := self.env.context.get(
                "project_documents_template_folder"
            )
        ) and any(
            (cond.field_expr, cond.operator) == ("type", "in")
            and "folder" in cond.value
            for cond in domain.iter_conditions()
        ):
            _debug.logic("template_folder_excluded", folder=template_folder_id)
            domain &= ~Domain("id", "child_of", template_folder_id)
        return domain

    def _project_folder_or_ancestor_in_self(self, project_folder):
        project_folder_ancestors = set(
            project_folder.sudo()._get_ancestor_ids(include_self=True)
        )
        return project_folder_ancestors & set(self.ids)

    @api.ondelete(at_uninstall=False)
    def unlink_except_project_folder(self) -> None:
        # custom folders assigned to company.documents_project_folder_id are protected by _unlink_except_company_folders
        project_folder = self.env.ref("document_project.document_project_folder")
        if self._project_folder_or_ancestor_in_self(project_folder):
            _debug.logic("unlink_refused", reason="project_base_folder", documents=self)
            raise UserError(
                self.env._(
                    'Uh-oh! The project app needs the "%s" folder, so you can’t delete it.',
                    project_folder.name,
                )
            )
        projects_with_folder = self.env["project.project"].search(
            [("documents_folder_id", "child_of", self.ids)]
        )
        if projects_with_folder:
            _debug.logic(
                "unlink_refused",
                reason="folder_used_by_projects",
                projects=projects_with_folder,
            )
            raise UserError(
                self.env._(
                    "This action can't be performed, as it would remove the folders used by the following projects:\n%(projects)s\nTo continue, choose different folders for these projects.",
                    projects="\n".join(
                        f"- {project.name}" for project in projects_with_folder
                    ),
                )
            )

    @api.model
    def _get_project_protected_folder_ids(self):
        """Return ids of folders that must never be deleted automatically.

        :return: ids of folders used by projects (including archived ones),
            their ancestors, and the base project folder with its ancestors
        :rtype: set of int
        """
        # The unlink_except_project_folder check uses child_of, meaning
        # deleting any ancestor of a project folder would also be blocked.
        # Archived projects must be included because DocumentsDocument.unlink
        # propagates active_test=False context to the ondelete check.
        project_folders = (
            self.env["project.project"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("documents_folder_id", "!=", False),
                ]
            )
            .mapped("documents_folder_id")
        )
        protected_ids = set()
        for folder in project_folders:
            if folder.parent_path:
                protected_ids.update(folder._get_ancestor_ids(include_self=True))
        # Also protect the base project folder and its ancestors
        project_folder = self.env.ref(
            "document_project.document_project_folder", raise_if_not_found=False
        )
        if project_folder and project_folder.parent_path:
            protected_ids.update(project_folder._get_ancestor_ids(include_self=True))
        return protected_ids

    @api.model
    def _get_domain_gc_clear_bin(self):
        domain = super()._get_domain_gc_clear_bin()
        # Exclude protected project folders to prevent UserError during
        # autovacuum (see _get_project_protected_folder_ids).
        if excluded_ids := self._get_project_protected_folder_ids():
            _debug.logic("gc_folders_protected", count=len(excluded_ids))
            domain = Domain.AND([domain, [("id", "not in", list(excluded_ids))]])
        return domain

    def _get_removable_parent_folders(self):
        """Exclude project folders from the opportunistic parent-folder cleanup.

        Deleting the last children of an archived project folder must not
        cascade into deleting the folder itself: unlink_except_project_folder
        would raise a UserError and roll back the whole unlink batch (this
        aborted the _gc_clear_bin autovacuum daily, see task 23528).
        """
        folders = super()._get_removable_parent_folders()
        if folders and (protected_ids := self._get_project_protected_folder_ids()):
            _debug.logic("parent_cleanup_protected", folders=folders)
            folders = folders.filtered(lambda folder: folder.id not in protected_ids)
        return folders

    @api.constrains("active")
    def _check_project_folder_active(self) -> None:
        if all(d.active for d in self):
            return
        project_base_folder = self.env.ref(
            "document_project.document_project_folder", raise_if_not_found=False
        )
        if (
            project_base_folder
            and project_base_folder in self
            and not project_base_folder.active
        ):
            _debug.logic("archive_refused", reason="project_base_folder")
            raise ValidationError(
                self.env._(
                    "You cannot archive the project base folder (%s).",
                    project_base_folder.name,
                )
            )

    @api.constrains("company_id")
    def _check_company_fits_projects_and_settings(self) -> None:
        folders = self.filtered(lambda d: d.type == "folder")
        if not folders:
            return
        project_base_folder = self.env.ref(
            "document_project.document_project_folder", raise_if_not_found=False
        )
        if project_base_folder in folders and project_base_folder.company_id:
            _debug.logic("company_refused", reason="project_base_folder")
            raise ValidationError(
                self.env._(
                    "You cannot set a company on the %s folder.",
                    project_base_folder.name,
                )
            )

        if companies_to_check := self.env["res.company"].search(
            [
                ("documents_project_folder_id", "in", folders.ids),
                ("documents_project_folder_id.company_id", "!=", False),
            ]
        ):
            if wrong_companies := companies_to_check.filtered(
                lambda c: (
                    c.documents_project_folder_id.company_id.id not in {False, c.id}
                )
            ):
                companies_list = "\n- ".join(
                    f"{company.name}: {company.documents_project_folder_id.name}"
                    for company in wrong_companies
                )
                _debug.logic(
                    "company_refused",
                    reason="cross_company_project_folder",
                    companies=wrong_companies,
                )
                raise ValidationError(
                    self.env._(
                        "Company Project Folders cannot be linked to another company.%s",
                        f"\n- {companies_list}",
                    )
                )

        for folder in folders:
            # a folder without a company serves projects of any company
            if not folder.company_id:
                continue
            if folder.project_ids and folder.project_ids.company_id:
                different_company_projects = folder.project_ids.filtered(
                    lambda p, folder=folder: p.company_id != folder.company_id
                )
                if not different_company_projects:
                    continue
                if len(different_company_projects) == 1:
                    project = different_company_projects[0]
                    message = self.env._(
                        'This folder should remain in the same company as the "%(project)s" project to which it is linked. Please update the company of the "%(project)s" project, or leave the company of this folder empty.',
                        project=project.name,
                    )
                else:
                    lines = [
                        f"- {project.name}" for project in different_company_projects
                    ]
                    message = self.env._(
                        "This folder should remain in the same company as the following projects to which it is linked:\n%s\n\nPlease update the company of those projects, or leave the company of this folder empty.",
                        "\n".join(lines),
                    )
                raise ValidationError(message)

    def write(self, vals):
        write_result = super().write(vals)
        if (
            "partner_id" not in vals
            and (folder_id := vals.get("folder_id"))
            and (documents_without_partner := self.filtered(lambda d: not d.partner_id))
            and (
                folder_values := self.env["document.document"]
                .browse(folder_id)
                ._prepare_link_to_project_vals()
            )
            and (partner := folder_values.get("partner_id"))
        ):
            documents_without_partner.partner_id = partner
        project_folder = self.env.ref("document_project.document_project_folder")
        if not vals.get("active", True) and self._project_folder_or_ancestor_in_self(
            project_folder
        ):
            raise UserError(
                self.env._(
                    'The "%s" folder is required by the Project application and cannot be archived.',
                    project_folder.name,
                )
            )
        return write_result

    def _prepare_link_to_project_vals(self) -> ValuesType:
        self.check_singleton()
        if self.type != "folder" or self.shortcut_document_id:
            return {}
        if project_sudo := self._get_project_from_closest_ancestor().sudo():
            return {
                "partner_id": project_sudo.partner_id.id,
            }
        return {}

    def _get_project_from_closest_ancestor(self):
        """
        If the current folder is linked to exactly one project, this method returns
        that project.

        If the current folder doesn't match the criteria, but one of its ancestors
        does, this method will return the project linked to the closest ancestor
        matching the criteria.

        :return: The project linked to the closest valid ancestor, or an empty
        recordset if no project is found.
        """
        self.check_singleton()
        eligible_projects = (
            self.env["project.project"]
            .sudo()
            ._read_group(
                [("documents_folder_id", "parent_of", self.id)],
                ["documents_folder_id"],
                having=[("__count", "=", 1)],
            )
        )
        if not eligible_projects:
            return self.env["project.project"]

        # dict {folder_id: position}, where position is a value used to sort projects by their folder_id
        folder_id_order = {
            folder_id: i
            for i, folder_id in enumerate(
                reversed(list(self._get_ancestor_ids(include_self=True)))
            )
        }
        eligible_projects.sort(
            key=lambda project_group: folder_id_order[project_group[0].id]
        )
        return (
            self.env["project.project"]
            .sudo()
            .search([("documents_folder_id", "=", eligible_projects[0][0].id)], limit=1)
            .sudo(False)
        )

    def _get_details_panel_res_models(self) -> list[str]:
        return [
            *super()._get_details_panel_res_models(),
            "project.project",
            "project.task",
        ]

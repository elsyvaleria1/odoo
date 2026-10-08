from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps

_debug = DebugLog(__name__)

# the visibilities that keep a project to its manager and its team
TEAM_ONLY = ("followers", "invited_users")
# what decides who reaches a project's documents
AUDIENCE_FIELDS = frozenset(
    {"privacy_visibility", "user_id", "member_user_ids", "documents_folder_id"}
)


class ProjectProject(models.Model):
    _name = "project.project"
    _inherit = ["project.project"]

    documents_folder_id = fields.Many2one(
        comodel_name="document.document",
        index="btree_not_null",
        copy=False,
        domain="[('type', '=', 'folder'), ('shortcut_document_id', '=', False), "
        "'|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        context=lambda env: {
            "default_folder_id": env.company.documents_project_folder_id.id,
        },
        help="Folder in which all of the documents of this project will be categorized.",
    )
    documents_folder_permission = fields.Selection(
        related="documents_folder_id.user_permission"
    )
    document_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_documents",
    )
    document_ids = fields.One2many(
        comodel_name="document.document",
        export_string_translation=False,
        compute="_compute_documents",
    )

    @api.ondelete(at_uninstall=False)
    def _archive_folder_on_projects_unlinked(self) -> None:
        """Archives the project folder if all its related projects are unlinked."""
        # an archived project still owns its folder
        folders = self.sudo().documents_folder_id.with_context(active_test=False)
        orphaned = folders.filtered(
            lambda folder: folder.active and not (folder.project_ids - self)
        )
        orphaned.with_env(self.env)._filtered_access("unlink").action_archive()

    @api.constrains("documents_folder_id")
    def _check_company_is_folders_company(self) -> None:
        for project in self.filtered("documents_folder_id"):
            if folder := project["documents_folder_id"]:
                if folder.company_id and project.company_id != folder.company_id:
                    _debug.logic(
                        "project_folder_refused",
                        reason="company_mismatch",
                        project=project,
                        folder=folder,
                    )
                    raise UserError(
                        self.env._(
                            'The "%(folder)s" folder should either be in the "%(company)s" company like this'
                            " project or be open to all companies.",
                            folder=folder.name,
                            company=project.company_id.name,
                        )
                    )

    @api.depends("documents_folder_id")
    def _compute_documents(self) -> None:
        documents = self.env["document.document"].search(
            [
                ("type", "in", ("binary", "url")),
                ("id", "child_of", self.documents_folder_id.ids),
            ]
        )
        _debug.perf.count("project_documents", projects=self, documents=len(documents))
        for project in self:
            document_ids = documents.browse(
                [
                    doc.id
                    for doc in documents
                    if doc._is_descendant_of(project.documents_folder_id)
                ]
            )
            project.document_ids = document_ids
            project.document_count = len(document_ids)

    def _create_missing_folders(self) -> None:
        folders_to_create_vals = []
        projects_with_folder_to_create = []
        documents_project_folder_id = self.env.company.documents_project_folder_id.id

        for project in self:
            if not project.documents_folder_id:
                team_only = project.privacy_visibility in TEAM_ONLY
                folder_vals = {
                    "access_internal": "none" if team_only else "edit",
                    "company_id": project.company_id.id,
                    "folder_id": documents_project_folder_id,
                    "name": project.name,
                    "type": "folder",
                }
                if team_only:
                    # a team's folder is not opened by the link its parent
                    # hands down: its members hold grants instead
                    folder_vals["access_via_link"] = "none"
                folders_to_create_vals.append(folder_vals)
                projects_with_folder_to_create.append(project)

        _debug.pipeline(
            "project_folders_created",
            projects=self,
            missing=len(folders_to_create_vals),
        )
        if folders_to_create_vals:
            created_folders = (
                self.env["document.document"].sudo().create(folders_to_create_vals)
            )
            for project, folder in zip(
                projects_with_folder_to_create, created_folders, strict=False
            ):
                project.sudo().documents_folder_id = folder
            self.browse(
                [project.id for project in projects_with_folder_to_create]
            )._sync_document_audience()

    def _sync_document_audience(self) -> None:
        # the project decides who reaches its folder: on a team-only project
        # its manager and its team, and on a shared one the portal users
        # invited as collaborators, each at what their collaboration allows.
        # The grants are the project's (cause), revoked when it asks no more
        Access = self.env["document.access"]
        for project in self:
            folder = project.documents_folder_id
            wanted = []
            if folder and project.privacy_visibility in TEAM_ONLY:
                wanted += [
                    (folder.id, "partner_id", user.partner_id.id, "edit", False)
                    for user in project.user_id | project.member_user_ids
                ]
            if folder and project.privacy_visibility in ("invited_users", "portal"):
                for collaboration in project.collaborator_ids:
                    role = "view" if collaboration.access_mode == "view" else "edit"
                    if collaboration.partner_id:
                        wanted.append(
                            (
                                folder.id,
                                "partner_id",
                                collaboration.partner_id.id,
                                role,
                                False,
                            )
                        )
                    elif collaboration.group_id:
                        wanted.append(
                            (
                                folder.id,
                                "group_id",
                                collaboration.group_id.id,
                                role,
                                collaboration.company_id.id or False,
                            )
                        )
            _debug.pipeline(
                "project_audience_synced",
                project=project,
                folder=folder,
                grants=len(wanted),
            )
            Access._sync_caused_grants(f"project.project,{project.id}", wanted)

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        if not self.env.context.get("no_create_folder"):
            projects._create_missing_folders()
        return projects

    def write(self, vals):
        if "company_id" in vals:
            for project in self:
                if (
                    project.documents_folder_id
                    and project.documents_folder_id.company_id
                    and len(project.documents_folder_id.project_ids) > 1
                ):
                    other_projects = project.documents_folder_id.project_ids - self
                    if (
                        other_projects
                        and other_projects.company_id.id != vals["company_id"]
                    ):
                        _debug.logic(
                            "project_company_refused",
                            reason="folder_shared",
                            project=project,
                            others=other_projects,
                        )
                        lines = [f"- {project.name}" for project in other_projects]
                        raise UserError(
                            self.env._(
                                'You cannot change the company of this project, because its folder is linked to the other following projects that are still in the "%(other_company)s" company:\n%(other_folders)s\n\n'
                                'Please update the company of all projects so that they remain in the same company as their folder, or leave the company of the "%(folder)s" folder blank.',
                                other_company=other_projects.company_id.name,
                                other_folders="\n".join(lines),
                                folder=project.documents_folder_id.name,
                            )
                        )

        if (
            "name" in vals
            and len(self.documents_folder_id.sudo().project_ids) == 1
            and self.name == self.documents_folder_id.sudo().name
        ):
            _debug.lifecycle("project_folder_renamed", project=self)
            self.documents_folder_id.sudo().name = vals["name"]

        if new_visibility := vals.get("privacy_visibility"):
            _debug.pipeline(
                "project_visibility_propagated",
                projects=self,
                visibility=new_visibility,
            )
            team_only = new_visibility in TEAM_ONLY
            for project in self.filtered("documents_folder_id"):
                folder = project.documents_folder_id
                # the folder and what it holds: closed to the company and to
                # its link for a team, open again as the parent hands it down
                (folder | project.document_ids).with_privilege(
                    "document.privilege_share_documents",
                    reason="a project's documents follow its visibility",
                ).action_update_access_rights(
                    access_internal="none" if team_only else "edit",
                    access_via_link="none"
                    if team_only
                    else (folder.folder_id.access_via_link or "none"),
                )
        project_root_documents = self.env["document.document"]
        if "documents_folder_id" in vals:
            project_root_documents = self.documents_folder_id.children_ids

        res = super().write(vals)
        if "company_id" in vals:
            for project in self:
                if (
                    project.documents_folder_id
                    and project.documents_folder_id.company_id
                ):
                    project.documents_folder_id.company_id = project.company_id
        if not self.env.context.get("no_create_folder"):
            self._create_missing_folders()
        if project_root_documents:
            project_root_documents.folder_id = self.documents_folder_id
        if AUDIENCE_FIELDS & vals.keys():
            self._sync_document_audience()

        return res

    def unlink(self):
        # a deleted project asks for no grant on the folder it leaves behind
        for project in self:
            self.env["document.access"]._sync_caused_grants(
                f"project.project,{project.id}", []
            )
        return super().unlink()

    def copy(self, default=None):
        # We have to add no_create_folder=True to the context, otherwise a folder
        # will be automatically created during the call to create.
        copied_projects = (
            super(ProjectProject, self.with_context(no_create_folder=True))
            .copy(default)
            .with_env(self.env)
        )

        for old_project, new_project in zip(self, copied_projects, strict=False):
            if (
                not self.env.context.get("no_create_folder")
                and old_project.documents_folder_id
            ):
                _debug.lifecycle(
                    "project_folder_copied", source=old_project, copy=new_project
                )
                new_project.documents_folder_id = (
                    old_project.documents_folder_id.sudo().copy(
                        {"name": new_project.name, "owner_id": False}
                    )
                )
        return copied_projects

    def _get_stat_buttons(self):
        buttons = super()._get_stat_buttons()
        if self.documents_folder_id.user_permission != "none":
            buttons.append(
                {
                    "icon": "file-text-o",
                    "text": self.env._("Documents"),
                    "number": self.document_count,
                    "action_type": "object",
                    "action": "action_view_documents_project",
                    "additional_context": json_dumps(
                        {
                            "active_id": self.id,
                        }
                    ),
                    "sequence": 20,
                }
            )
        return buttons

    def action_view_documents_project(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "document.document_action_preference"
        )
        default_user_folder_id = (
            str(self.documents_folder_id.id) if self.documents_folder_id else False
        )
        return action | {
            "view_mode": "kanban,list",
            "context": {
                "active_id": self.id,
                "active_model": "project.project",
                "searchpanel_default_user_folder_id": default_user_folder_id,
                "no_documents_unique_folder_id": True,
            },
        }

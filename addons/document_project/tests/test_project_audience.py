from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestProjectAudience(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = (
            "base.group_user,project.group_project_user,document.group_documents_user"
        )
        cls.manager = new_test_user(cls.env, "aud_manager", groups=groups)
        cls.member = new_test_user(cls.env, "aud_member", groups=groups)
        cls.bystander = new_test_user(cls.env, "aud_bystander", groups=groups)
        cls.portal = new_test_user(cls.env, "aud_portal", groups="base.group_portal")

    def _permission(self, record, user):
        record.invalidate_recordset()
        return record.with_user(user).user_permission

    def _team_project(self, **vals):
        return self.env["project.project"].create(
            {
                "name": "Team only",
                "privacy_visibility": "followers",
                "user_id": self.manager.id,
                "member_user_ids": [Command.set(self.member.ids)],
                **vals,
            }
        )

    def test_a_team_only_project_is_its_teams(self):
        project = self._team_project()
        folder = project.documents_folder_id
        inside = self.env["document.document"].create(
            {"name": "plan.txt", "folder_id": folder.id}
        )
        self.assertEqual(folder.access_via_link, "none")
        for record in (folder, inside):
            self.assertEqual(self._permission(record, self.bystander), "none")
            self.assertEqual(self._permission(record, self.member), "edit")
            self.assertEqual(self._permission(record, self.manager), "edit")

    def test_the_team_moves_the_grants(self):
        project = self._team_project()
        folder = project.documents_folder_id
        project.member_user_ids = [Command.link(self.bystander.id)]
        self.assertEqual(self._permission(folder, self.bystander), "edit")
        project.member_user_ids = [Command.unlink(self.member.id)]
        self.assertEqual(self._permission(folder, self.member), "none")

    def test_an_invited_collaborator_holds_what_the_collaboration_allows(self):
        project = self._team_project(privacy_visibility="invited_users")
        self.env["project.collaborator"].create(
            {"project_id": project.id, "partner_id": self.portal.partner_id.id}
        )
        folder = project.documents_folder_id
        self.assertEqual(self._permission(folder, self.portal), "view")
        self.assertEqual(self._permission(folder, self.bystander), "none")
        project.collaborator_ids.unlink()
        self.assertEqual(self._permission(folder, self.portal), "none")

    def test_the_visibility_opens_and_closes_the_folder(self):
        project = self._team_project()
        folder = project.documents_folder_id
        project.privacy_visibility = "employees"
        self.assertEqual(self._permission(folder, self.bystander), "edit")
        self.assertEqual(folder.access_via_link, folder.folder_id.access_via_link)
        project.privacy_visibility = "invited_users"
        self.assertEqual(self._permission(folder, self.bystander), "none")
        self.assertEqual(folder.access_via_link, "none")
        self.assertEqual(self._permission(folder, self.member), "edit")

    def test_a_deleted_project_leaves_no_grant(self):
        project = self._team_project()
        folder = project.documents_folder_id
        project.unlink()
        self.assertFalse(
            self.env["document.access"].search(
                [("cause_ref", "=", f"project.project,{project.id}")]
            )
        )
        self.assertEqual(self._permission(folder, self.member), "none")

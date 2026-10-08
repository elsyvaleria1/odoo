from odoo import Command
from odoo.fields import Domain
from odoo.tests import tagged

from .test_project_base import TestProjectCommon


@tagged("post_install", "-at_install")
class TestProjectReviewCollaborator(TestProjectCommon):
    def _share(self, project, partner, access_mode="edit"):
        self.env["wizard.project.project.share"].create(
            {
                "res_model": "project.project",
                "res_id": project.id,
                "collaborator_ids": [
                    Command.create(
                        {"partner_id": partner.id, "access_mode": access_mode}
                    )
                ],
            }
        ).action_send_mail()

    def _live_links(self, records, partner):
        return (
            self.env["access.link"]
            .with_privilege("base.privilege_resolve_links", reason="test")
            ._record_links(records, Domain("partner_id", "=", partner.id))
        )

    def test_removing_a_collaborator_revokes_their_links(self) -> None:
        project = self.env["project.project"].create(
            {"name": "Shared", "privacy_visibility": "portal"}
        )
        task = self.env["project.task"].create(
            {"name": "Task", "project_id": project.id}
        )
        partner = self.user_portal.partner_id
        self._share(project, partner)
        task.message_subscribe(partner_ids=partner.ids)
        task._portal_tokens(partner)
        self.assertTrue(self._live_links(project, partner))
        self.assertTrue(self._live_links(task, partner))
        self.assertIn(partner, task.message_partner_ids)

        project.collaborator_ids.unlink()

        self.assertFalse(self._live_links(project, partner))
        self.assertFalse(self._live_links(task, partner))
        self.assertNotIn(partner, task.message_partner_ids)
        self.assertNotIn(partner, project.message_partner_ids)

    def test_removing_a_collaborator_keeps_other_partners_links(self) -> None:
        project = self.env["project.project"].create(
            {"name": "Shared", "privacy_visibility": "portal"}
        )
        partner = self.user_portal.partner_id
        other = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Other portal",
                    "login": "other_portal",
                    "email": "o@example.com",
                    "group_ids": [Command.set(self.env.ref("base.group_portal").ids)],
                }
            )
            .partner_id
        )
        self._share(project, partner)
        self._share(project, other)
        project.message_subscribe(partner_ids=(partner | other).ids)
        project.collaborator_ids.filtered(lambda c: c.partner_id == partner).unlink()
        self.assertTrue(self._live_links(project, other))
        self.assertIn(other, project.message_partner_ids)

    def test_last_collaborator_counts_every_company(self) -> None:
        rule = self.env.ref("project.project_task_rule_portal_project_sharing")
        company_b = self.env["res.company"].create({"name": "Collab Co"})
        project_b = self.env["project.project"].create(
            {"name": "B", "privacy_visibility": "portal", "company_id": company_b.id}
        )
        project_a = self.env["project.project"].create(
            {
                "name": "A",
                "privacy_visibility": "portal",
                "company_id": self.env.company.id,
            }
        )
        project_b._add_collaborators(self.partner_2)
        project_a._add_collaborators(self.partner_3)
        self.assertTrue(rule.active)
        self.partner_2.company_id = False
        self.partner_3.company_id = False
        manager = self.user_projectmanager
        manager.company_ids = self.env.company
        project_a.with_user(manager).collaborator_ids.unlink()
        self.assertTrue(rule.active)

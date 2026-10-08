import re
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from odoo.addons.project.tests.test_project_base import TestProjectCommon

JUNK_TOKEN = "x" * 24


def _links(env, record):
    return env["access.link"]._record_links(record)


@tagged("post_install", "-at_install")
class TestProjectReviewPortalPages(TestProjectCommon, HttpCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project_pigs.privacy_visibility = "portal"
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.user_employee = Users.create(
            {
                "name": "Review Employee",
                "login": "review_employee",
                "email": "review.employee@example.com",
                "group_ids": [Command.set(cls.env.ref("base.group_user").ids)],
            }
        )
        cls.user_nobody = Users.create(
            {
                "name": "Review Nobody",
                "login": "review_nobody",
                "email": "review.nobody@example.com",
                "group_ids": [Command.set([])],
            }
        )

    def test_task_list_shows_nothing_to_a_user_who_reads_no_task(self) -> None:
        self.assertFalse(
            self.env["project.task"].with_user(self.user_nobody).has_access("read")
        )
        self.authenticate(self.user_nobody.login, self.user_nobody.login)
        response = self.url_open("/my/tasks")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.task_1.name, response.text)
        self.assertNotIn(self.task_2.name, response.text)

    def test_a_junk_token_does_not_widen_what_a_session_sees(self) -> None:
        company_b = self.env["res.company"].create({"name": "Review Company B"})
        project = self.env["project.project"].create(
            {
                "name": "Review Companyless Project",
                "privacy_visibility": "employees",
                "company_id": False,
            }
        )
        hidden = self.env["project.task"].create(
            {
                "name": "Review Company B Task",
                "project_id": project.id,
                "company_id": company_b.id,
            }
        )
        user = self.user_projectuser
        self.assertTrue(project.with_user(user).has_access("read"))
        self.assertFalse(hidden.with_user(user).has_access("read"))
        self.authenticate(user.login, user.login)
        url = f"/my/projects/{project.id}/task/{hidden.id}"
        self.assertNotIn(hidden.name, self.url_open(url).text)
        self.assertNotIn(
            hidden.name, self.url_open(f"{url}?access_token={JUNK_TOKEN}").text
        )

    def test_a_signed_in_link_holder_sees_the_tasks_the_link_opens(self) -> None:
        token = self.project_pigs._portal_get_or_create_token()
        self.assertFalse(
            self.project_pigs.with_user(self.user_portal).has_access("read")
        )
        self.authenticate(self.user_portal.login, self.user_portal.login)
        response = self.url_open(
            f"/my/projects/{self.project_pigs.id}?access_token={token}"
        )
        self.assertIn(self.task_1.name, response.text)

    def test_task_pager_links_carry_only_the_presented_token(self) -> None:
        pigs = self.project_pigs
        token = pigs._portal_get_or_create_token()
        neighbour_links = _links(self.env, self.task_1 | self.task_2)
        self.authenticate(None, None)
        self.url_open(f"/my/projects/{pigs.id}?access_token={token}")
        response = self.url_open(
            f"/my/projects/{pigs.id}/task/{self.task_1.id}?access_token={token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("record_pager", response.text)
        pager_urls = re.findall(
            rf'href="(/my/projects/{pigs.id}/task/\d+[^"]*)"', response.text
        )
        self.assertTrue(pager_urls)
        for url in pager_urls:
            self.assertNotIn("res_id=", url)
            self.assertIn(f"access_token={token}", url)
        self.assertEqual(_links(self.env, self.task_1 | self.task_2), neighbour_links)

    def test_task_pager_links_of_a_session_carry_no_token(self) -> None:
        project = self.env["project.project"].create(
            {"name": "Review Pager Project", "privacy_visibility": "employees"}
        )
        first, __ = self.env["project.task"].create(
            [
                {"name": "Review Pager One", "project_id": project.id},
                {"name": "Review Pager Two", "project_id": project.id},
            ]
        )
        self.authenticate(
            self.user_projectmanager.login, self.user_projectmanager.login
        )
        self.url_open(f"/my/projects/{project.id}")
        response = self.url_open(f"/my/projects/{project.id}/task/{first.id}")
        self.assertIn("record_pager", response.text)
        self.assertNotIn("access_token=None", response.text)
        self.assertNotIn("model=project.project", response.text)

    def test_project_sharing_task_page_drops_the_task_pager(self) -> None:
        self.authenticate(
            self.user_projectmanager.login, self.user_projectmanager.login
        )
        self.url_open("/my/tasks")
        task_url = f"/my/tasks/{self.task_1.id}"
        self.assertIn("record_pager", self.url_open(task_url).text)
        response = self.url_open(f"{task_url}?project_sharing=1")
        self.assertNotIn("record_pager", response.text)

    def test_sorting_by_status_keeps_the_groups_in_order(self) -> None:
        project = self.env["project.project"].create(
            {
                "name": "Review Grouped Project",
                "privacy_visibility": "employees",
                "workflow_step_ids": [
                    Command.create({"name": "Review Alpha Step", "sequence": 1}),
                    Command.create({"name": "Review Zulu Step", "sequence": 2}),
                ],
            }
        )
        alpha, zulu = project.workflow_step_ids.sorted("sequence")
        self.env["project.task"].create(
            [
                {
                    "name": "Review Alpha Task",
                    "project_id": project.id,
                    "step_id": alpha.id,
                    "state": "todo",
                },
                {
                    "name": "Review Zulu Task",
                    "project_id": project.id,
                    "step_id": zulu.id,
                    "state": "approved",
                },
            ]
        )
        self.authenticate(
            self.user_projectmanager.login, self.user_projectmanager.login
        )
        text = self.url_open(
            f"/my/projects/{project.id}?groupby=step_id&sortby=state"
        ).text
        self.assertLess(text.index("Review Alpha Task"), text.index("Review Zulu Task"))

    def test_subtasks_of_a_task_outside_the_project_are_not_found(self) -> None:
        other = self.env["project.project"].create(
            {"name": "Review Other Project", "privacy_visibility": "employees"}
        )
        foreign = self.env["project.task"].create(
            {
                "name": "Review Foreign Parent",
                "project_id": other.id,
                "child_ids": [
                    Command.create(
                        {"name": "Review Foreign Child", "project_id": other.id}
                    )
                ],
            }
        )
        self.authenticate(
            self.user_projectmanager.login, self.user_projectmanager.login
        )
        response = self.url_open(
            f"/my/projects/{self.project_pigs.id}/task/{foreign.id}/subtasks"
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Review Foreign Child", response.text)

    def test_a_read_only_employee_shares_a_project_in_view_mode(self) -> None:
        self.authenticate(self.user_employee.login, self.user_employee.login)
        response = self.url_open(f"/my/projects/{self.project_pigs.id}/project_sharing")
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.text, r'"project_sharing_access_mode":\s*"view"')

    def test_task_filters_name_only_projects_with_listed_tasks(self) -> None:
        self.env["project.project"].create(
            {"name": "Review Empty Filter Project", "privacy_visibility": "employees"}
        )
        self.authenticate(self.user_projectuser.login, self.user_projectuser.login)
        text = self.url_open("/my/tasks").text
        self.assertIn(self.task_1.name, text)
        self.assertIn(self.project_pigs.name, text)
        self.assertNotIn("Review Empty Filter Project", text)

    def test_task_page_hands_the_chatter_only_the_presented_token(self) -> None:
        customer_token = self.task_1._portal_get_or_create_token()
        self.authenticate(
            self.user_projectmanager.login, self.user_projectmanager.login
        )
        response = self.url_open(f"/my/tasks/{self.task_1.id}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(customer_token, response.text)


@tagged("post_install", "-at_install")
class TestProjectReviewShareWizards(TestProjectCommon):
    def _task_share_wizard(self, task):
        return (
            self.env["wizard.project.task.share"]
            .with_context(active_model="project.task", active_id=task.id)
            .create({"partner_ids": [Command.link(self.partner_2.id)]})
        )

    def test_task_share_wizard_refuses_a_team_only_project(self) -> None:
        task = self.env["project.task"].create(
            {"name": "Review Goats Task", "project_id": self.project_goats.id}
        )
        links = _links(self.env, task)
        wizard = self._task_share_wizard(task)
        self.assertEqual(wizard.task_id, task)
        self.assertEqual(wizard.project_privacy_visibility, "followers")
        self.assertFalse(wizard.share_link)
        with self.assertRaises(UserError):
            wizard.action_send_mail()
        self.assertEqual(_links(self.env, task), links)

    def test_task_share_wizard_sends_a_task_of_a_portal_project(self) -> None:
        self.project_pigs.privacy_visibility = "portal"
        wizard = self._task_share_wizard(self.task_1)
        self.assertEqual(wizard.task_id, self.task_1)
        wizard.action_send_mail()
        self.assertIn(self.partner_2, self.task_1.message_partner_ids)

    def _project_share_wizard(self, project):
        return (
            self.env["wizard.project.project.share"]
            .with_context(active_model="project.project", active_id=project.id)
            .create({})
        )

    def test_opening_the_project_share_dialog_issues_no_link(self) -> None:
        pigs = self.project_pigs
        pigs.privacy_visibility = "portal"
        links = _links(self.env, pigs)
        wizard = self._project_share_wizard(pigs)
        self.assertFalse(wizard.share_link)
        self.assertEqual(_links(self.env, pigs), links)
        wizard.action_issue_share_link()
        issued = _links(self.env, pigs) - links
        self.assertEqual(len(issued), 1)
        self.assertTrue(wizard.share_link)
        reopened = self._project_share_wizard(pigs)
        self.assertEqual(reopened.share_link, wizard.share_link)
        self.assertEqual(_links(self.env, pigs) - links, issued)

    def test_project_share_wizard_leaves_group_and_lapsed_grants_alone(self) -> None:
        pigs = self.project_pigs
        pigs.privacy_visibility = "portal"
        Collaborator = self.env["project.collaborator"]
        group_grant = Collaborator.create(
            {"project_id": pigs.id, "group_id": self.env.ref("base.group_portal").id}
        )
        lapsed = Collaborator.create(
            {
                "project_id": pigs.id,
                "partner_id": self.partner_2.id,
                "date_to": fields.Datetime.now() - timedelta(days=1),
            }
        )
        live = Collaborator.create(
            {"project_id": pigs.id, "partner_id": self.partner_3.id}
        )
        wizard = self._project_share_wizard(pigs)
        self.assertIn(self.partner_3, wizard.collaborator_ids.partner_id)
        self.assertNotIn(self.partner_2, wizard.collaborator_ids.partner_id)
        wizard.action_send_mail()
        self.assertEqual(
            (group_grant | lapsed | live).exists(), group_grant | lapsed | live
        )
        self.assertTrue(lapsed.date_to)

        wizard = self._project_share_wizard(pigs)
        wizard.collaborator_ids = [
            Command.create({"partner_id": self.partner_2.id, "access_mode": "edit"})
        ]
        wizard.action_send_mail()
        self.assertEqual(
            (group_grant | lapsed | live).exists(), group_grant | lapsed | live
        )
        self.assertFalse(lapsed.date_to)
        self.assertEqual(lapsed.access_mode, "edit")


@tagged("post_install", "-at_install")
class TestProjectReviewAccessRows(TestProjectCommon):
    def test_only_managers_reach_the_create_from_template_wizards(self) -> None:
        for model in (
            "wizard.project.project.create.from.template",
            "wizard.project.project.create.from.template.mapping",
        ):
            self.assertFalse(
                self.env[model].with_user(self.user_projectuser).has_access("read")
            )
            self.assertTrue(
                self.env[model].with_user(self.user_projectmanager).has_access("create")
            )

    def test_a_project_user_deletes_a_step_through_the_wizard(self) -> None:
        step = self.env["project.workflow.step"].create(
            {"name": "Review Disposable Step", "project_ids": self.project_pigs.ids}
        )
        action = step.with_user(self.user_projectuser).action_open_delete_wizard()
        wizard = (
            self.env[action["res_model"]]
            .with_user(self.user_projectuser)
            .browse(action["res_id"])
        )
        wizard.action_unlink()
        self.assertFalse(step.exists())

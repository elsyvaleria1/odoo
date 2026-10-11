import html
import re
from datetime import timedelta
from urllib.parse import urlsplit

from odoo import Command, fields
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .test_project_base import TestProjectCommon


class ProjectLinkHttpCase(TestProjectCommon, HttpCase):
    def setUp(self) -> None:
        super().setUp()
        self.authenticate(None, None)

    def _opens(self, url: str) -> bool:
        response = self.url_open(url, allow_redirects=False)
        self.assertIn(response.status_code, (200, 303), url)
        return response.status_code == 200

    def _project_page(self, project, token: str) -> bool:
        return self._opens(f"/my/projects/{project.id}?access_token={token}")

    def _project_task_page(self, project, task, token: str) -> bool:
        return self._opens(
            f"/my/projects/{project.id}/task/{task.id}?access_token={token}"
        )

    def _task_page(self, task, token: str) -> bool:
        return self._opens(f"/my/tasks/{task.id}?access_token={token}")

    def _rpc(self, route: str, params: dict) -> dict:
        return self.url_open(
            route, json={"jsonrpc": "2.0", "method": "call", "params": params}
        ).json()

    def _fetch(self, thread, credentials: dict) -> dict | None:
        reply = self._rpc(
            "/mail/chatter_fetch",
            {"thread_model": thread._name, "thread_id": thread.id, **credentials},
        )
        return None if "error" in reply else reply["result"]

    def _post(self, thread, body: str, credentials: dict) -> bool:
        reply = self._rpc(
            "/mail/message/post",
            {
                "thread_model": thread._name,
                "thread_id": thread.id,
                "post_data": {"body": body},
                **credentials,
            },
        )
        return "error" not in reply

    def _page_credentials(self, project, task, token: str) -> dict[str, str]:
        response = self.url_open(
            f"/my/projects/{project.id}/task/{task.id}?access_token={token}"
        )
        self.assertEqual(response.status_code, 200)
        discussion = re.search(r'<div[^>]*id="discussion"[^>]*>', response.text)
        self.assertTrue(discussion, "the task page renders its chatter")
        return {
            key: value
            for key, value in re.findall(
                r'data-(token|pid|hash)="([^"]*)"', discussion[0]
            )
            if value
        }


@tagged("post_install", "-at_install", "access_link")
class TestProjectLinkChatterIdentity(ProjectLinkHttpCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project_pigs.privacy_visibility = "portal"
        cls.customer = cls.project_pigs.partner_id
        cls.customer_token = cls.project_pigs._portal_get_or_create_token()
        cls.own_message, cls.other_message = (
            cls.env["mail.message"]
            .sudo()
            .create(
                [
                    {
                        "model": cls.task_1._name,
                        "res_id": cls.task_1.id,
                        "message_type": "comment",
                        "subtype_id": cls.env.ref("mail.mt_comment").id,
                        "body": f"Written by {author.name}",
                        "author_id": author.id,
                        "attachment_ids": [
                            Command.create(
                                {
                                    "name": f"{author.name}.txt",
                                    "raw": b"attached",
                                    "res_model": cls.task_1._name,
                                    "res_id": cls.task_1.id,
                                }
                            )
                        ],
                    }
                    for author in (cls.customer, cls.partner_2)
                ]
            )
        )

    def _owned(self, credentials: dict) -> dict[int, bool]:
        result = self._fetch(self.task_1, credentials)
        self.assertIsNotNone(result, "the history loads")
        return {
            message["id"]: "ownership_token" in message["attachment_ids"][0]
            for message in result["data"]["mail.message"]
            if message["id"] in (self.own_message | self.other_message).ids
        }

    def test_the_history_marks_the_visitors_own_messages_as_theirs(self) -> None:
        credentials = self._page_credentials(
            self.project_pigs, self.task_1, self.customer_token
        )
        self.assertEqual(set(credentials), {"token", "pid", "hash"})
        self.assertEqual(
            self._owned(credentials),
            {self.own_message.id: True, self.other_message.id: False},
        )

    def test_a_bare_project_token_owns_nothing_in_the_history(self) -> None:
        self.assertEqual(
            self._owned({"token": self.customer_token}),
            {self.own_message.id: False, self.other_message.id: False},
        )

    @mute_logger("odoo.http")
    def test_a_hash_signed_for_someone_else_owns_nothing(self) -> None:
        credentials = self._page_credentials(
            self.project_pigs, self.task_1, self.customer_token
        )
        forged = dict(credentials, pid=str(self.partner_2.id))
        self.assertEqual(
            self._owned(forged),
            {self.own_message.id: False, self.other_message.id: False},
        )

    def test_the_visitor_edits_their_own_message_and_no_other(self) -> None:
        credentials = self._page_credentials(
            self.project_pigs, self.task_1, self.customer_token
        )
        for message, editable in (
            (self.own_message, True),
            (self.other_message, False),
        ):
            with self.subTest(author=message.author_id.name):
                reply = self._rpc(
                    "/mail/message/update_content",
                    {
                        "message_id": message.id,
                        "update_data": {"body": "Edited", "attachment_ids": []},
                        **credentials,
                    },
                )
                self.assertEqual("error" not in reply, editable)


@tagged("post_install", "-at_install", "access_link")
class TestProjectLinkPrivacy(ProjectLinkHttpCase):
    def _project(self, visibility: str):
        project = (
            self.env["project.project"]
            .with_context(mail_create_nolog=True)
            .create(
                {
                    "name": f"Sheep ({visibility})",
                    "privacy_visibility": visibility,
                    "partner_id": self.partner_1.id,
                }
            )
        )
        task = (
            self.env["project.task"]
            .with_context(mail_create_nolog=True)
            .create({"name": "Shear", "project_id": project.id})
        )
        return project, task

    def _issue_links(self, project, task) -> dict[str, str]:
        Link = self.env["access.link"]
        return {
            "customer": project._portal_get_or_create_token(self.partner_1),
            "public": Link._issue(project, role="view", cause="share")[1],
            "stranger": project._portal_get_or_create_token(self.partner_2),
            "task": Link._issue(
                task, partner=self.partner_1, role="comment", cause="notification"
            )[1],
        }

    def _reach(self, project, task, tokens: dict[str, str]) -> dict[str, bool]:
        reach = {}
        for name in ("customer", "public", "stranger"):
            token = tokens[name]
            reach[name] = self._project_page(project, token)
            reach[f"{name}/task"] = self._project_task_page(project, task, token)
            reach[f"{name}/chatter"] = self._fetch(task, {"token": token}) is not None
        reach["task"] = self._task_page(task, tokens["task"])
        reach["task/chatter"] = self._fetch(task, {"token": tokens["task"]}) is not None
        return reach

    @staticmethod
    def _everything(reach: dict[str, bool], opened: bool) -> dict[str, bool]:
        return dict.fromkeys(reach, opened)

    @mute_logger("odoo.http")
    def test_links_open_a_portal_or_employees_project_and_its_tasks(self) -> None:
        for visibility in ("portal", "employees"):
            with self.subTest(visibility=visibility):
                project, task = self._project(visibility)
                reach = self._reach(project, task, self._issue_links(project, task))
                self.assertEqual(reach, self._everything(reach, True))

    @mute_logger("odoo.http")
    def test_no_link_opens_a_followers_project_or_its_tasks(self) -> None:
        project, task = self._project("followers")
        tokens = self._issue_links(project, task)
        reach = self._reach(project, task, tokens)
        self.assertEqual(reach, self._everything(reach, False))

    @mute_logger("odoo.http")
    def test_no_signed_link_speaks_on_a_followers_project(self) -> None:
        project, task = self._project("followers")
        tokens = self._issue_links(project, task)
        signed = {
            "token": tokens["customer"],
            "pid": self.partner_1.id,
            "hash": project._sign_token(self.partner_1.id, token=tokens["customer"]),
        }
        unsigned_hash = dict(signed)
        del unsigned_hash["token"]
        task_signed = {
            "token": tokens["task"],
            "pid": self.partner_1.id,
            "hash": task._sign_token(self.partner_1.id, token=tokens["task"]),
        }
        for thread, credentials in (
            (project, signed),
            (project, unsigned_hash),
            (task, task_signed),
            (task, {k: v for k, v in task_signed.items() if k != "token"}),
        ):
            with self.subTest(model=thread._name, keys=sorted(credentials)):
                self.assertIsNone(self._fetch(thread, credentials))
                self.assertFalse(self._post(thread, "Through a link", credentials))
        self.assertFalse(project.website_message_ids | task.website_message_ids)

    @mute_logger("odoo.http")
    def test_links_issued_before_a_switch_to_followers_close_with_it(self) -> None:
        project, task = self._project("employees")
        tokens = self._issue_links(project, task)
        Link = self.env["access.link"]
        links = Link._record_links(project) | Link._record_links(task)
        reach = self._reach(project, task, tokens)
        self.assertEqual(reach, self._everything(reach, True))

        project.privacy_visibility = "followers"
        self.assertEqual(
            Link._record_links(project) | Link._record_links(task),
            links,
            "nothing is revoked: the privacy is read when a link is presented",
        )
        reach = self._reach(project, task, tokens)
        self.assertEqual(reach, self._everything(reach, False))

        project.privacy_visibility = "employees"
        reach = self._reach(project, task, tokens)
        self.assertEqual(reach, self._everything(reach, True))

    @mute_logger("odoo.http")
    def test_invited_users_opens_only_for_a_live_collaborator(self) -> None:
        project, task = self._project("portal")
        project._add_collaborators(self.partner_1, access_mode="view")
        tokens = self._issue_links(project, task)
        project.privacy_visibility = "invited_users"
        reach = self._reach(project, task, tokens)
        self.assertEqual(
            reach,
            {
                **self._everything(reach, False),
                "customer": True,
                "customer/task": True,
                "customer/chatter": True,
                "task": True,
                "task/chatter": True,
            },
        )

        project.collaborator_ids.date_to = fields.Datetime.now() - timedelta(days=1)
        reach = self._reach(project, task, tokens)
        self.assertEqual(reach, self._everything(reach, False))

    @mute_logger("odoo.http")
    def test_invited_users_opens_a_task_for_its_follower(self) -> None:
        project, task = self._project("invited_users")
        Link = self.env["access.link"]
        __, token = Link._issue(
            task, partner=self.partner_3, role="comment", cause="notification"
        )
        self.assertFalse(self._task_page(task, token))
        task.message_subscribe(partner_ids=self.partner_3.ids)
        self.assertTrue(self._task_page(task, token))
        self.assertIsNotNone(self._fetch(task, {"token": token}))
        __, project_token = Link._issue(
            project, partner=self.partner_3, role="comment", cause="notification"
        )
        self.assertFalse(self._project_page(project, project_token))
        self.assertFalse(self._project_task_page(project, task, project_token))

    def test_an_invitation_opens_an_invited_users_project(self) -> None:
        project, __ = self._project("invited_users")
        guest = self.user_portal.partner_id
        self.env["wizard.project.project.share"].create(
            {
                "res_model": project._name,
                "res_id": project.id,
                "collaborator_ids": [
                    Command.create({"partner_id": guest.id, "access_mode": "view"})
                ],
            }
        ).action_send_mail()
        invitation = self.env["mail.message"].search(
            [
                ("model", "=", project._name),
                ("res_id", "=", project.id),
                ("partner_ids", "in", guest.ids),
            ],
            limit=1,
        )
        url = re.search(r'href="([^"]*/mail/view[^"]*)"', invitation.body)
        self.assertTrue(url, "the invitation carries a link")
        parts = urlsplit(html.unescape(url[1]))
        response = self.url_open(f"{parts.path}?{parts.query}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(urlsplit(response.url).path, f"/my/projects/{project.id}")
        self.assertIn(project.name, response.text)

    def test_the_customers_notification_link_opens_a_portal_project(self) -> None:
        project, __ = self._project("portal")
        url = project._get_share_url(redirect=True, pid=self.partner_1.id)
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(urlsplit(response.url).path, f"/my/projects/{project.id}")
        self.assertIn(project.name, response.text)

    def test_the_customer_is_offered_a_button_only_where_their_link_opens(
        self,
    ) -> None:
        project, task = self._project("invited_users")
        task.partner_id = self.partner_1
        task.message_unsubscribe(partner_ids=self.partner_1.ids)

        def customer_button(record) -> bool:
            groups = record._notify_get_recipients_groups(
                self.env["mail.message"], False
            )
            return next(
                data["has_button_access"]
                for name, __, data in groups
                if name == "portal_customer"
            )

        self.assertFalse(customer_button(project))
        self.assertFalse(customer_button(task))
        project._add_collaborators(self.partner_1, access_mode="view")
        self.assertTrue(customer_button(project))
        self.assertTrue(customer_button(task))

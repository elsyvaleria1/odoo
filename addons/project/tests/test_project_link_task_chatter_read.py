import re

from odoo import http
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged
from odoo.tools import file_open, mute_logger

from .test_project_base import TestProjectCommon


@tagged("post_install", "-at_install", "access_link")
class TestProjectLinkTaskChatterRead(TestProjectCommon, HttpCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project_pigs.privacy_visibility = "portal"
        cls.customer = cls.project_pigs.partner_id
        cls.customer_token = cls.project_pigs._portal_get_or_create_token()
        __, cls.public_token = cls.env["access.link"]._issue(
            cls.project_pigs, role="view", cause="share"
        )
        cls.comment = cls.task_1.message_post(
            body="Customer-visible comment",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        cls.note = cls.task_1.message_post(
            body="Internal note",
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

    def setUp(self) -> None:
        super().setUp()
        self.authenticate(None, None)

    def _page_credentials(self, token: str, task=None) -> dict[str, str]:
        task = task or self.task_1
        response = self.url_open(
            f"/my/projects/{self.project_pigs.id}/task/{task.id}?access_token={token}"
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

    def _rpc(self, route: str, params: dict) -> dict:
        return self.url_open(
            route, json={"jsonrpc": "2.0", "method": "call", "params": params}
        ).json()

    def _init(self, task, credentials: dict) -> dict | None:
        reply = self._rpc(
            "/portal/chatter_init",
            {"thread_model": task._name, "thread_id": task.id, **credentials},
        )
        threads = reply["result"].get("mixin.mail.thread", [])
        return next((t for t in threads if t["id"] == task.id), None)

    def _fetch(self, task, credentials: dict) -> list[int] | None:
        reply = self._rpc(
            "/mail/chatter_fetch",
            {"thread_model": task._name, "thread_id": task.id, **credentials},
        )
        return None if "error" in reply else reply["result"]["messages"]

    def _post(self, task, body: str, credentials: dict) -> bool:
        reply = self._rpc(
            "/mail/message/post",
            {
                "thread_model": task._name,
                "thread_id": task.id,
                "post_data": {"body": body},
                **credentials,
            },
        )
        return "error" not in reply

    def _react(self, message, credentials: dict) -> bool:
        reply = self._rpc(
            "/mail/message/reaction",
            {"message_id": message.id, "content": "👍", "action": "add", **credentials},
        )
        return "error" not in reply

    def _upload(self, task, credentials: dict) -> int:
        with file_open("addons/web/__init__.py") as file:
            return self.url_open(
                "/mail/attachment/upload",
                data={
                    "csrf_token": http.Request.csrf_token(self),
                    "thread_id": task.id,
                    "thread_model": task._name,
                    **credentials,
                },
                files={"ufile": file},
            ).status_code

    def _avatar(self, message, token: str) -> bytes:
        return self.url_open(
            f"/mail/avatar/mail.message/{message.id}/author_avatar/50x50"
            f"?access_token={token}"
        ).content

    def _foreign_task(self):
        return self.env["project.task"].create(
            {"name": "Goat task", "project_id": self.project_goats.id}
        )

    @mute_logger("odoo.http")
    def test_the_customers_link_reads_and_speaks_in_the_task_chatter(self) -> None:
        credentials = self._page_credentials(self.customer_token)
        self.assertEqual(
            set(credentials), {"token", "pid", "hash"}, "the page signs the chatter"
        )
        thread = self._init(self.task_1, credentials)
        self.assertTrue(thread, "the chatter opens")
        self.assertIs(thread["can_post"], True)
        self.assertIs(thread["can_react"], True)
        messages = self._fetch(self.task_1, credentials)
        self.assertIsNotNone(messages, "the history loads")
        self.assertIn(self.comment.id, messages)
        self.assertNotIn(self.note.id, messages)
        self.assertTrue(self._react(self.comment, credentials))
        self.assertEqual(self.comment.reaction_ids.partner_id, self.customer)
        self.assertEqual(self._upload(self.task_1, credentials), 200)
        self.assertTrue(self._post(self.task_1, "Customer replies", credentials))

    @mute_logger("odoo.http")
    def test_the_public_link_reads_the_task_chatter_and_speaks_nowhere(self) -> None:
        credentials = self._page_credentials(self.public_token)
        self.assertEqual(
            credentials, {"token": self.public_token}, "a view link signs nothing"
        )
        thread = self._init(self.task_1, credentials)
        self.assertTrue(thread, "the chatter opens")
        self.assertIs(thread["can_post"], False)
        self.assertIs(thread["can_react"], False)
        messages = self._fetch(self.task_1, credentials)
        self.assertIsNotNone(messages, "the history loads")
        self.assertIn(self.comment.id, messages)
        self.assertNotIn(self.note.id, messages)
        self.assertFalse(self._post(self.task_1, "Public reply", credentials))
        self.assertFalse(self._react(self.comment, credentials))
        self.assertEqual(self._upload(self.task_1, credentials), 404)
        self.assertFalse(self.comment.reaction_ids)

    @mute_logger("odoo.http")
    def test_a_bare_project_token_reads_but_speaks_for_nobody(self) -> None:
        credentials = {"token": self.customer_token}
        self.assertIsNotNone(self._fetch(self.task_1, credentials))
        self.assertIs(self._init(self.task_1, credentials)["can_post"], False)
        self.assertFalse(self._post(self.task_1, "Unsigned reply", credentials))
        self.assertFalse(self._react(self.comment, credentials))
        self.assertEqual(self._upload(self.task_1, credentials), 404)

    def test_the_link_shows_its_task_message_avatars(self) -> None:
        refused = self._avatar(self.comment, "x" * 32)
        for token in (self.customer_token, self.public_token):
            with self.subTest(token=token == self.public_token and "public"):
                self.assertNotEqual(self._avatar(self.comment, token), refused)

    @mute_logger("odoo.http")
    def test_the_link_reads_no_archived_template_or_foreign_task(self) -> None:
        template = self.env["project.task"].create(
            {
                "name": "Template",
                "project_id": self.project_pigs.id,
                "is_template": True,
            }
        )
        self.task_2.active = False
        for token in (self.customer_token, self.public_token):
            for task in (self.task_2, template, self._foreign_task()):
                with self.subTest(task=task.name, token=token == self.public_token):
                    self.assertIsNone(self._fetch(task, {"token": token}))
                    self.assertIsNone(self._init(task, {"token": token}))

    def test_a_revoked_link_reads_nothing(self) -> None:
        credentials = self._page_credentials(self.public_token)
        self.env["access.link"].sudo()._revoke_record_links(self.project_pigs, "test")
        self.assertIsNone(self._fetch(self.task_1, credentials))
        self.assertIsNone(self._init(self.task_1, credentials))


@tagged("post_install", "-at_install", "access_link")
class TestProjectShareDialogPrivacy(TestProjectCommon):
    def _wizard(self):
        return (
            self.env["wizard.project.project.share"]
            .with_user(self.user_projectmanager)
            .with_context(
                active_model="project.project", active_id=self.project_pigs.id
            )
            .create({})
        )

    def test_a_project_closed_to_links_issues_none(self) -> None:
        for visibility in ("followers", "invited_users"):
            with self.subTest(visibility=visibility):
                self.project_pigs.privacy_visibility = visibility
                links = self.env["access.link"]._record_links(self.project_pigs)
                wizard = self._wizard()
                with self.assertRaises(UserError):
                    wizard.action_issue_share_link()
                self.assertFalse(wizard.share_link)
                self.assertEqual(
                    self.env["access.link"]._record_links(self.project_pigs), links
                )

    def test_a_portal_project_issues_its_public_link(self) -> None:
        self.project_pigs.privacy_visibility = "portal"
        wizard = self._wizard()
        wizard.action_issue_share_link()
        self.assertTrue(wizard.share_link)

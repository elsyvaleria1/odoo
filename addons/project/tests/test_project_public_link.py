import re
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from odoo import fields
from odoo.fields import Domain
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .test_project_base import TestProjectCommon
from odoo.addons.base.models.access_link import hash_token


@tagged("post_install", "-at_install", "access_link")
class TestProjectPublicLink(TestProjectCommon, HttpCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project_pigs.privacy_visibility = "portal"
        cls.Link = cls.env["access.link"]

    def _wizard(self):
        return (
            self.env["wizard.project.project.share"]
            .with_user(self.user_projectmanager)
            .with_context(
                active_model="project.project", active_id=self.project_pigs.id
            )
            .create({})
        )

    def _issue_public_link(self) -> str:
        wizard = self._wizard()
        wizard.action_issue_share_link()
        self.assertTrue(wizard.share_link)
        return wizard.share_link

    @staticmethod
    def _token_of(url: str) -> str:
        (token,) = parse_qs(urlsplit(url).query)["access_token"]
        return token

    @staticmethod
    def _path_of(url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.path}?{parts.query}"

    def _link_of(self, token: str):
        return self.Link.sudo().search(Domain("token_hash", "=", hash_token(token)))

    def _rpc(self, route: str, params: dict) -> dict:
        return self.url_open(
            route, json={"jsonrpc": "2.0", "method": "call", "params": params}
        ).json()

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

    def _messages(self, thread, body: str):
        return (
            self.env["mail.message"]
            .sudo()
            .search(
                Domain("model", "=", thread._name)
                & Domain("res_id", "=", thread.id)
                & Domain("body", "ilike", body)
            )
        )

    def _task_page_credentials(self, token: str) -> dict[str, str]:
        response = self.url_open(
            f"/my/projects/{self.project_pigs.id}/task/{self.task_1.id}"
            f"?access_token={token}"
        )
        self.assertEqual(response.status_code, 200)
        discussion = re.search(r'<div[^>]*id="discussion"[^>]*>', response.text)
        self.assertTrue(discussion, "the task page renders its chatter")
        return dict(re.findall(r'data-(token|pid|hash)="([^"]*)"', discussion[0]))

    def test_the_public_link_is_a_partnerless_view_link_shared_by_hand(self) -> None:
        customer_token = self.project_pigs._portal_get_or_create_token()
        token = self._token_of(self._issue_public_link())
        self.assertNotEqual(token, customer_token)
        link = self._link_of(token)
        self.assertEqual(
            (link.role, link.audience, link.cause, link.partner_id),
            ("view", "anyone", "share", self.env["res.partner"]),
        )
        self.assertAlmostEqual(
            link.date_to,
            fields.Datetime.now() + timedelta(days=30),
            delta=timedelta(minutes=5),
        )
        self.project_pigs.invalidate_recordset(["access_token"])
        self.assertEqual(self.project_pigs.access_token, customer_token)

    def test_the_dialog_shows_the_live_public_link_and_issues_none(self) -> None:
        self.project_pigs._portal_get_or_create_token()
        links = self.Link._record_links(self.project_pigs)
        self.assertFalse(
            self._wizard().share_link, "the customer's link is not the public one"
        )
        self.assertEqual(self.Link._record_links(self.project_pigs), links)

        share_link = self._issue_public_link()
        self.assertEqual(self._wizard().share_link, share_link)

        link = self._link_of(self._token_of(share_link))
        link.sudo().date_to = fields.Datetime.now() - timedelta(minutes=1)
        self.assertFalse(self._wizard().share_link, "an expired link is not shown")
        link.sudo().date_to = fields.Datetime.now() + timedelta(days=1)
        self.assertEqual(self._wizard().share_link, share_link)
        link.with_user(self.user_projectmanager).action_revoke()
        self.assertFalse(self._wizard().share_link, "a revoked link is not shown")

    def test_revoking_the_public_link_leaves_the_customers_link(self) -> None:
        customer_token = self.project_pigs._portal_get_or_create_token()
        public = self._link_of(self._token_of(self._issue_public_link()))
        public.with_user(self.user_projectmanager).action_revoke()
        self.assertTrue(self.project_pigs._portal_token_opens(customer_token))

    def test_the_public_link_opens_the_project_and_its_tasks(self) -> None:
        share_link = self._issue_public_link()
        token = self._token_of(share_link)
        response = self.url_open(self._path_of(share_link))
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"/my/projects/{self.project_pigs.id}", response.url)
        self.assertIn(self.task_1.name, response.text)
        response = self.url_open(
            f"/my/projects/{self.project_pigs.id}/task/{self.task_1.id}"
            f"?access_token={token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.task_1.name, response.text)

    @mute_logger("odoo.http")
    def test_the_public_link_posts_nowhere(self) -> None:
        token = self._token_of(self._issue_public_link())
        from_page = self._task_page_credentials(token)
        customer = self.project_pigs.partner_id
        forged = {
            "token": token,
            "pid": customer.id,
            "hash": self.project_pigs._sign_token(customer.id, token=token),
        }
        for thread in (self.project_pigs, self.task_1):
            for name, credentials in (
                ("token", {"token": token}),
                ("page", {"token": token, **from_page}),
                ("hash", forged),
            ):
                with self.subTest(model=thread._name, credentials=name):
                    body = f"Public {thread._name} {name}"
                    self.assertFalse(self._post(thread, body, credentials))
                    self.assertFalse(self._messages(thread, body))

    def test_the_customers_notification_link_still_posts(self) -> None:
        self._issue_public_link()
        token = self.project_pigs._portal_get_or_create_token()
        customer = self.project_pigs.partner_id
        signed = {
            "token": token,
            "pid": customer.id,
            "hash": self.project_pigs._sign_token(customer.id, token=token),
        }
        self.assertTrue(self._post(self.project_pigs, "Customer on project", signed))
        self.assertTrue(self._post(self.task_1, "Customer on task", signed))
        self.assertEqual(
            self._messages(self.project_pigs, "Customer on project").author_id,
            customer,
        )
        self.assertEqual(
            self._messages(self.task_1, "Customer on task").author_id, customer
        )


@tagged("post_install", "-at_install", "access_link")
class TestFindReusableLink(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Link = cls.env["access.link"]

    def _find(self, **kwargs):
        return self.Link._get_link_and_token_reusable(self.project_pigs, **kwargs)

    def test_nothing_issued_finds_nothing_and_issues_nothing(self) -> None:
        links = self.Link._record_links(self.project_pigs)
        self.assertEqual(self._find(), (self.Link, None))
        self.assertEqual(self.Link._record_links(self.project_pigs), links)

    def test_it_finds_what_issue_would_reuse(self) -> None:
        issued, token = self.Link._issue(self.project_pigs, cause="share")
        self.assertEqual(self._find(cause="share"), (issued, token))
        self.assertEqual(
            self.Link._issue(self.project_pigs, cause="share"), (issued, token)
        )

    def test_it_matches_partner_role_and_cause(self) -> None:
        self.Link._issue(
            self.project_pigs,
            partner=self.partner_1,
            role="comment",
            cause="notification",
        )
        for kwargs in (
            {"cause": "share"},
            {"cause": "notification"},
            {"role": "comment", "cause": "share"},
            {"partner": self.partner_2, "role": "comment", "cause": "notification"},
        ):
            with self.subTest(**kwargs):
                self.assertEqual(self._find(**kwargs), (self.Link, None))
        link, token = self._find(
            partner=self.partner_1, role="comment", cause="notification"
        )
        self.assertTrue(link)
        self.assertTrue(token)

    def test_a_revoked_or_expired_link_is_not_reusable(self) -> None:
        issued, _token = self.Link._issue(self.project_pigs, cause="share")
        issued.sudo().date_to = fields.Datetime.now() - timedelta(minutes=1)
        self.assertEqual(self._find(cause="share"), (self.Link, None))
        issued.sudo().date_to = fields.Datetime.now() + timedelta(days=1)
        issued.action_revoke()
        self.assertEqual(self._find(cause="share"), (self.Link, None))

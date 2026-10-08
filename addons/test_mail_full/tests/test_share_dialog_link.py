import re
from datetime import timedelta
from html import unescape
from urllib.parse import parse_qs, urlsplit

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.base.models.access_link import hash_token
from odoo.addons.mail.tests.common import MockEmail


@tagged("-at_install", "post_install", "portal", "access_link")
class TestShareDialogLink(MockEmail, HttpCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Link = cls.env["access.link"]
        cls.customer = cls.env["res.partner"].create(
            {"name": "Dialog Customer", "email": "dialog.customer@example.com"}
        )
        cls.record = cls.env["mail.test.portal"].create(
            {"name": "Dialog Shared Record", "partner_id": cls.customer.id}
        )
        cls.opening = cls.record.message_post(
            body="Opening message",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        cls.sharer = new_test_user(
            cls.env,
            "dialog_sharer",
            groups="base.group_user,base.group_partner_manager",
        )
        cls.recipient = new_test_user(
            cls.env,
            "dialog_recipient",
            groups="base.group_portal",
            email="dialog.recipient@example.com",
        ).partner_id

    def _wizard(self, **values):
        return (
            self.env["wizard.mail.message.send.portal.link"]
            .with_user(self.sharer)
            .with_context(active_model=self.record._name, active_id=self.record.id)
            .create(values)
        )

    def _issue_dialog_link(self) -> str:
        wizard = self._wizard()
        wizard.action_issue_share_link()
        self.assertTrue(wizard.share_link)
        return wizard.share_link

    @staticmethod
    def _query(url: str) -> dict[str, str]:
        return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}

    @staticmethod
    def _path_of(url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.path}?{parts.query}"

    def _link_of(self, token: str):
        return self.Link.sudo().search(Domain("token_hash", "=", hash_token(token)))

    def _links(self):
        return self.Link.sudo().search(
            Domain("res_model", "=", self.record._name)
            & Domain("res_id", "=", self.record.id)
        )

    def _rpc(self, route: str, **params) -> dict:
        return self.url_open(route, json={"params": params}).json()

    def _post(self, body: str, **credentials) -> dict:
        return self._rpc(
            "/mail/message/post",
            thread_model=self.record._name,
            thread_id=self.record.id,
            post_data={"body": body},
            **credentials,
        )

    def _posted(self, body: str):
        self.env.invalidate_all()
        return self.record.message_ids.filtered(lambda message: body in message.body)

    def test_the_dialog_link_is_a_partnerless_view_link(self) -> None:
        customer_token = self.record._portal_get_or_create_token()
        token = self._query(self._issue_dialog_link())["access_token"]
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

    def test_reading_the_dialog_issues_nothing(self) -> None:
        self.assertFalse(self._links())
        self.assertFalse(self._wizard().share_link)
        self.assertFalse(self._links(), "opening the dialog issues no link")

        self.record._portal_get_or_create_token()
        links = self._links()
        self.assertFalse(
            self._wizard().share_link, "the customer's link is not the dialog's"
        )
        self.assertEqual(self._links(), links)

    def test_the_button_issues_one_link_and_the_dialog_shows_it(self) -> None:
        wizard = self._wizard()
        action = wizard.action_issue_share_link()
        self.assertEqual(
            (action["res_model"], action["res_id"], action["target"]),
            (wizard._name, wizard.id, "new"),
        )
        share_link = wizard.share_link
        links = self._links()
        self.assertEqual(len(links), 1)
        self.assertEqual(self._wizard().share_link, share_link)
        self._wizard().action_issue_share_link()
        self.assertEqual(self._links(), links, "a live link is handed out again")

        links.with_user(self.sharer).action_revoke()
        self.assertFalse(self._wizard().share_link, "a revoked link is not shown")

    def test_the_dialog_link_opens_the_record(self) -> None:
        share_link = self._issue_dialog_link()
        token = self._query(share_link)["access_token"]
        self.authenticate(None, None)
        response = self.url_open(self._path_of(share_link))
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"/my/test_portal/{self.record.id}", response.url)
        self.assertEqual(self._query(response.url)["access_token"], token)
        fetched = self._rpc(
            "/mail/chatter_fetch",
            thread_model=self.record._name,
            thread_id=self.record.id,
            token=token,
        )
        self.assertIn(self.opening.id, fetched["result"]["messages"])

    @mute_logger("odoo.http")
    def test_the_dialog_link_posts_and_reacts_as_nobody(self) -> None:
        token = self._query(self._issue_dialog_link())["access_token"]
        forged = {
            "token": token,
            "pid": self.customer.id,
            "hash": self.record._sign_token(self.customer.id, token=token),
        }
        self.authenticate(None, None)
        for name, credentials in (("token", {"token": token}), ("hash", forged)):
            with self.subTest(credentials=name):
                body = f"Posted with the dialog's link and its {name}"
                self.assertIn("error", self._post(body, **credentials))
                self.assertFalse(self._posted(body))
                reaction = self._rpc(
                    "/mail/message/reaction",
                    message_id=self.opening.id,
                    content="👍",
                    action="add",
                    **credentials,
                )
                self.assertIn("error", reaction)
        self.env.invalidate_all()
        self.assertFalse(self.opening.reaction_ids)

    def test_sending_without_recipients_is_refused(self) -> None:
        wizard = self._wizard()
        with self.mock_mail_gateway(), self.assertRaises(UserError):
            wizard.action_send_mail()
        self.assertNotSentEmail()
        self.assertFalse(self._links())

    def test_an_e_mailed_recipient_link_still_posts_as_the_recipient(self) -> None:
        wizard = self._wizard(partner_ids=[Command.set(self.recipient.ids)])
        with self.mock_mail_gateway():
            wizard.action_send_mail()
        invitation = self.env["mail.message"].search(
            Domain("model", "=", self.record._name)
            & Domain("res_id", "=", self.record.id)
            & Domain("partner_ids", "in", self.recipient.ids)
            & Domain("body", "like", "access_token=")
        )
        self.assertEqual(len(invitation), 1)
        href = unescape(re.search(r'href="([^"]+)"', str(invitation.body))[1])
        query = self._query(href)
        self.assertEqual(int(query["pid"]), self.recipient.id)
        link = self._link_of(query["access_token"])
        self.assertEqual((link.role, link.partner_id), ("comment", self.recipient))
        self.authenticate(None, None)
        body = "Posted from the e-mailed invitation"
        self.assertNotIn(
            "error",
            self._post(
                body, token=query["access_token"], pid=query["pid"], hash=query["hash"]
            ),
        )
        self.assertEqual(self._posted(body).author_id, self.recipient)

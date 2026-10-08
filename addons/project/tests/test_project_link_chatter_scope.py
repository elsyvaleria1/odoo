import re

from odoo.fields import Domain
from odoo.tests import HttpCase, new_test_user, tagged

from .test_project_base import TestProjectCommon


@tagged("post_install", "-at_install")
class TestProjectLinkChatterScope(TestProjectCommon, HttpCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project_pigs.privacy_visibility = "portal"
        cls.customer_token = cls.project_pigs._portal_get_or_create_token()
        cls.link_partner = cls.partner_2
        __, cls.link_token = cls.env["access.link"]._issue(
            cls.project_pigs, partner=cls.link_partner, role="comment"
        )
        cls.stranger = new_test_user(
            cls.env, login="stranger", password="stranger", groups="base.group_portal"
        )

    def _credentials(self, task) -> dict[str, str]:
        response = self.url_open(
            f"/my/projects/{self.project_pigs.id}/task/{task.id}"
            f"?access_token={self.link_token}"
        )
        self.assertEqual(response.status_code, 200)
        discussion = re.search(r'<div[^>]*id="discussion"[^>]*>', response.text)
        self.assertTrue(discussion, "the task page renders its chatter")
        return dict(re.findall(r'data-(token|pid|hash)="([^"]*)"', discussion[0]))

    def _rpc(self, route, params) -> dict:
        return self.url_open(
            route, json={"jsonrpc": "2.0", "method": "call", "params": params}
        ).json()

    def _post(self, thread, body, credentials) -> bool:
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

    def _edit(self, message, body, credentials) -> bool:
        reply = self._rpc(
            "/mail/message/update_content",
            {
                "message_id": message.id,
                "update_data": {"body": body, "attachment_ids": []},
                **credentials,
            },
        )
        return "error" not in reply

    def _react(self, message, credentials) -> bool:
        reply = self._rpc(
            "/mail/message/reaction",
            {"message_id": message.id, "content": "👍", "action": "add", **credentials},
        )
        return "error" not in reply

    def _messages(self, thread, body):
        return (
            self.env["mail.message"]
            .sudo()
            .search(
                Domain("model", "=", thread._name)
                & Domain("res_id", "=", thread.id)
                & Domain("body", "ilike", body)
            )
        )

    def _written_by_link_partner(self, task, body, subtype_xmlid="mail.mt_comment"):
        return task.message_post(
            body=body,
            author_id=self.link_partner.id,
            message_type="comment",
            subtype_xmlid=subtype_xmlid,
        )

    def _signed(self, partner, token) -> dict:
        return {
            "token": token,
            "pid": partner.id,
            "hash": self.project_pigs._sign_token(partner.id, token=token),
        }

    def test_the_link_posts_on_an_active_task_as_its_partner(self) -> None:
        credentials = self._credentials(self.task_1)
        self.assertTrue(self._post(self.task_1, "From the link", credentials))
        message = self._messages(self.task_1, "From the link")
        self.assertEqual(message.author_id, self.link_partner)

    def test_the_link_cannot_post_on_an_archived_task(self) -> None:
        credentials = self._credentials(self.task_1)
        self.task_2.active = False
        self.assertFalse(self._post(self.task_2, "On the archive", credentials))
        self.authenticate("stranger", "stranger")
        self.assertFalse(self._post(self.task_2, "Stranger on archive", credentials))
        self.assertFalse(
            self._messages(self.task_2, "On the archive")
            | self._messages(self.task_2, "Stranger on archive")
        )

    def test_the_link_neither_opens_nor_posts_on_a_template_task(self) -> None:
        credentials = self._credentials(self.task_1)
        template = self.env["project.task"].create(
            {
                "name": "Template",
                "project_id": self.project_pigs.id,
                "is_template": True,
            }
        )
        response = self.url_open(
            f"/my/projects/{self.project_pigs.id}/task/{template.id}"
            f"?access_token={self.link_token}",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertFalse(self._post(template, "On the template", credentials))
        self.assertFalse(self._messages(template, "On the template"))

    def test_the_link_edits_its_partners_comment_where_it_reaches(self) -> None:
        credentials = self._credentials(self.task_1)
        message = self._written_by_link_partner(self.task_2, "Partner wrote")
        self.assertTrue(self._edit(message, "Partner rewrote", credentials))
        self.assertIn("Partner rewrote", message.body)

    def test_the_link_neither_edits_nor_reacts_to_an_internal_note(self) -> None:
        credentials = self._credentials(self.task_1)
        note = self._written_by_link_partner(
            self.task_2, "Internal note", subtype_xmlid="mail.mt_note"
        )
        self.assertFalse(self._edit(note, "Rewritten note", credentials))
        self.assertFalse(self._react(note, credentials))
        self.authenticate("stranger", "stranger")
        self.assertFalse(self._react(note, credentials))
        self.assertIn("Internal note", note.body)
        self.assertFalse(note.reaction_ids)

    def test_the_customers_project_hash_needs_the_customers_link(self) -> None:
        signed = self._signed(self.partner_1, self.customer_token)
        token_less = {"pid": signed["pid"], "hash": signed["hash"]}
        self.assertFalse(self._post(self.task_1, "Bare hash", token_less))
        self.assertFalse(
            self._post(self.task_1, "Foreign token", {**signed, "token": "x" * 32})
        )
        self.assertTrue(self._post(self.task_1, "Customer link", signed))
        self.assertFalse(self._messages(self.task_1, "Bare hash"))
        self.assertEqual(
            self._messages(self.task_1, "Customer link").author_id, self.partner_1
        )

    def test_a_customer_link_lowered_to_view_no_longer_posts_on_tasks(self) -> None:
        signed = self._signed(self.partner_1, self.customer_token)
        self.env["access.link"]._update_record_links(
            self.project_pigs,
            {"role": "view"},
            Domain("partner_id", "=", self.partner_1.id),
        )
        self.assertFalse(self._post(self.task_1, "Viewer with hash", signed))
        token_less = {"pid": signed["pid"], "hash": signed["hash"]}
        self.assertFalse(self._post(self.task_1, "Viewer bare hash", token_less))

    def test_the_customers_own_task_link_still_posts(self) -> None:
        token = self.task_1._portal_get_or_create_token(self.partner_1)
        credentials = {
            "token": token,
            "pid": self.partner_1.id,
            "hash": self.task_1._sign_token(self.partner_1.id, token=token),
        }
        self.assertTrue(self._post(self.task_1, "Task link", credentials))
        self.assertEqual(
            self._messages(self.task_1, "Task link").author_id, self.partner_1
        )

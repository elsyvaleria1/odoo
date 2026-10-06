from urllib.parse import urlparse

from odoo import Command, http
from odoo.exceptions import UserError
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestArticleAccessRequest(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor = new_test_user(
            cls.env, login="kb_access_editor", groups="base.group_user"
        )
        cls.reader = new_test_user(
            cls.env, login="kb_access_reader", groups="base.group_user"
        )
        cls.asker = new_test_user(
            cls.env, login="kb_access_asker", groups="base.group_user"
        )
        cls.article = cls.env["knowledge.article"].create(
            {
                "name": "Members Only",
                "internal_permission": "none",
                "article_member_ids": [
                    Command.create(
                        {"partner_id": cls.editor.partner_id.id, "permission": "write"}
                    ),
                    Command.create(
                        {"partner_id": cls.reader.partner_id.id, "permission": "read"}
                    ),
                ],
            }
        )
        cls.child = cls.env["knowledge.article"].create(
            {"name": "Child", "parent_id": cls.article.id}
        )

    def _row(self, request):
        return request.approver_ids.filtered(lambda row: row.user_id == self.editor)

    def _ask(self, user, role):
        return (
            self.article.with_user(user).sudo()._request_access(user.partner_id, role)
        )

    def test_the_editors_are_asked_and_not_the_readers(self):
        self.assertEqual(self.article.access_approver_user_ids, self.editor)
        self.assertEqual(self.child.access_approver_user_ids, self.editor)

        request = self._ask(self.asker, "read")

        self.assertIn(self.editor, request.approver_ids.user_id)
        self.assertNotIn(self.reader, request.approver_ids.user_id)
        asked = request.approver_ids.filtered(lambda row: row._is_notifiable())
        self.assertEqual(asked.user_id, self.editor)

    def test_approving_invites_the_asker_with_the_role_asked_for(self):
        request = self._ask(self.asker, "write")

        request.with_user(self.editor).action_approve(approver=self._row(request))

        self.assertEqual(self.article.with_user(self.asker).user_permission, "write")
        self.assertTrue(self.child.with_user(self.asker).user_has_access)

    def test_the_access_already_held_is_not_asked_for(self):
        with self.assertRaises(UserError):
            self._ask(self.reader, "read")
        self.assertEqual(self._ask(self.reader, "write").state, "pending")

    def test_only_read_or_write_is_asked_for(self):
        with self.assertRaises(UserError):
            self._ask(self.asker, "none")

    def test_refusing_invites_nobody(self):
        request = self._ask(self.asker, "read")

        request.with_user(self.editor).action_refuse(approver=self._row(request))

        self.assertEqual(request.state, "refused")
        self.assertFalse(self.article.with_user(self.asker).user_has_access)

    def test_an_employee_refused_an_article_is_offered_a_request(self):
        self.authenticate("kb_access_asker", "kb_access_asker")
        path = f"/knowledge/article/{self.article.id}"

        response = self.url_open(path, allow_redirects=False)

        self.assertEqual(
            urlparse(response.headers["Location"]).path, f"{path}/request_access"
        )
        page = self.url_open(f"{path}/request_access")
        self.assertIn("Request to read", page.text)
        self.assertNotIn("Members Only", page.text)

        self.url_open(
            f"{path}/request_access",
            data={"role": "read", "csrf_token": http.Request.csrf_token(self)},
        )

        request = self.article.sudo()._get_live_access_request(
            self.asker.partner_id, "read"
        )
        self.assertEqual(request.request_owner_id, self.asker)
        self.assertIn(
            "Your request to read it is waiting",
            self.url_open(f"{path}/request_access").text,
        )

    def test_a_reader_opens_the_article_as_before(self):
        self.authenticate("kb_access_reader", "kb_access_reader")
        path = f"/knowledge/article/{self.article.id}"

        response = self.url_open(path, allow_redirects=False)

        self.assertNotIn("request_access", response.headers.get("Location", ""))

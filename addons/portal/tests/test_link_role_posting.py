from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger


@tagged("-at_install", "post_install", "access_link")
class TestLinkRolePosting(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create(
            {"name": "Link Holder", "email": "holder@example.com"}
        )
        cls.record = cls.env["res.partner"].create({"name": "Shared Record"})
        cls.opening = cls.record.message_post(
            body="Opening message",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    def setUp(self):
        super().setUp()
        self.patch(
            self.env.registry["res.partner"], "_mail_post_token_field", "signup_type"
        )
        self.authenticate(None, None)

    def _token(self, role):
        __, token = (
            self.env["access.link"]
            .sudo()
            ._issue(self.record, partner=self.customer, role=role, cause="share")
        )
        return token

    def _signed(self, token):
        return {
            "token": token,
            "pid": self.customer.id,
            "hash": self.record._sign_token(self.customer.id, token=token),
        }

    def _rpc(self, route, **params):
        return self.url_open(route, json={"params": params}).json()

    def _post(self, body, **credentials):
        return self._rpc(
            "/mail/message/post",
            thread_model=self.record._name,
            thread_id=self.record.id,
            post_data={"body": body},
            **credentials,
        )

    def _posted(self, body):
        self.env.invalidate_all()
        return self.record.message_ids.filtered(lambda message: body in message.body)

    def _react(self, **credentials):
        return self._rpc(
            "/mail/message/reaction",
            message_id=self.opening.id,
            content="👍",
            action="add",
            **credentials,
        )

    def test_a_view_link_reads_the_thread(self):
        token = self._token("view")
        fetched = self._rpc(
            "/mail/chatter_fetch",
            thread_model=self.record._name,
            thread_id=self.record.id,
            token=token,
        )
        self.assertIn(self.opening.id, fetched["result"]["messages"])
        init = self._rpc(
            "/portal/chatter_init",
            thread_model=self.record._name,
            thread_id=self.record.id,
            token=token,
        )
        (thread,) = init["result"]["mixin.mail.thread"]
        self.assertFalse(thread["can_react"], "a reader reacts to nothing")
        self.assertNotIn("portal_partner", thread, "a reader speaks as nobody")

    @mute_logger("odoo.http")
    def test_a_view_link_cannot_post(self):
        token = self._token("view")
        for name, credentials in (
            ("token", {"token": token}),
            ("token and hash", self._signed(token)),
        ):
            with self.subTest(name):
                body = f"Posted by a reader with a {name}"
                self.assertIn("error", self._post(body, **credentials))
                self.assertFalse(self._posted(body))

    @mute_logger("odoo.http")
    def test_a_view_link_cannot_react(self):
        token = self._token("view")
        for credentials in ({"token": token}, self._signed(token)):
            with self.subTest(credentials=sorted(credentials)):
                self.assertIn("error", self._react(**credentials))
        self.env.invalidate_all()
        self.assertFalse(self.opening.reaction_ids)

    def test_a_comment_or_edit_link_posts_as_its_partner(self):
        for role in ("comment", "edit"):
            token = self._token(role)
            for name, credentials in (
                ("token", {"token": token}),
                ("token and hash", self._signed(token)),
            ):
                with self.subTest(role=role, credentials=name):
                    body = f"Posted through a {role} link with a {name}"
                    self.assertNotIn("error", self._post(body, **credentials))
                    self.assertEqual(self._posted(body).author_id, self.customer)

    def test_a_comment_link_reacts_as_its_partner(self):
        self.assertNotIn("error", self._react(token=self._token("comment")))
        self.env.invalidate_all()
        self.assertEqual(self.opening.reaction_ids.partner_id, self.customer)

    @mute_logger("odoo.http")
    def test_a_guest_reacts_through_a_comment_link_and_not_a_view_link(self):
        guest = self.env["mail.guest"].create({"name": "Visitor"})
        self.opener.cookies[guest._cookie_name] = guest._format_auth_cookie()
        self.assertIn("error", self._react(token=self._token("view")))
        self.env.invalidate_all()
        self.assertFalse(self.opening.reaction_ids)

        self.assertNotIn("error", self._react(token=self._token("comment")))
        self.env.invalidate_all()
        self.assertEqual(
            (self.opening.reaction_ids.partner_id, self.opening.reaction_ids.guest_id),
            (self.customer, self.env["mail.guest"]),
        )

    def _chatter_init(self, **credentials):
        init = self._rpc(
            "/portal/chatter_init",
            thread_model=self.record._name,
            thread_id=self.record.id,
            **credentials,
        )
        (thread,) = init["result"]["mixin.mail.thread"]
        return thread

    def test_the_chatter_offers_posting_only_where_posting_is_granted(self):
        for role, granted in (("view", False), ("comment", True), ("edit", True)):
            token = self._token(role)
            for name, credentials in (
                ("token", {"token": token}),
                ("token and hash", self._signed(token)),
            ):
                with self.subTest(role=role, credentials=name):
                    thread = self._chatter_init(**credentials)
                    self.assertIs(thread["can_post"], granted)
                    self.assertIs(thread["can_react"], granted)

    def test_the_chatter_offers_posting_to_a_user_with_the_right(self):
        self.authenticate("admin", "admin")
        thread = self._chatter_init()
        self.assertIs(thread["can_post"], True)

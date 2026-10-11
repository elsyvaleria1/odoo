from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged, users
from odoo.tests.common import HttpCase
from odoo.tools import html_escape, mute_logger

from odoo.addons.auth_signup.models.res_partner import ResPartner
from odoo.addons.mail.tests.common import MailCommon
from odoo.addons.test_mail_full.tests.common import TestMailFullCommon
from odoo.addons.test_mail_sms.tests.common import TestSMSRecipients


@tagged("portal")
class TestPortal(TestMailFullCommon, TestSMSRecipients):
    def setUp(self):
        super().setUp()

        self.record_portal = self.env["mail.test.portal"].create(
            {
                "partner_id": self.partner_1.id,
                "name": "Test Portal Record",
            }
        )
        self.record_portal._portal_get_or_create_token()


@tagged("-at_install", "post_install", "portal", "mail_controller")
class TestPortalControllers(TestPortal):
    def test_portal_avatar_with_access_token(self):
        mail_record = self.env["mail.message"].create(
            {
                "author_id": self.record_portal.partner_id.id,
                "model": self.record_portal._name,
                "res_id": self.record_portal.id,
            }
        )
        token = self.record_portal.access_token
        formatted_record = mail_record.portal_message_format(options={"token": token})[
            0
        ]
        self.assertEqual(
            formatted_record.get("author_avatar_url"),
            f"/mail/avatar/mail.message/{mail_record.id}/author_avatar/50x50?access_token={token}",
        )
        response = self.url_open(
            f"/mail/avatar/mail.message/{mail_record.id}/author_avatar/50x50?access_token={token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Content-Type"), "image/svg+xml; charset=utf-8"
        )
        self.assertRegex(
            response.headers.get("Content-Disposition", ""),
            r"mail_message-\d+-author_avatar\.svg",
        )

        placeholder_response = self.url_open(
            f"/mail/avatar/mail.message/{mail_record.id}/author_avatar/50x50?access_token={token + 'a'}"
        )
        self.assertEqual(placeholder_response.status_code, 200)
        self.assertEqual(placeholder_response.headers.get("Content-Type"), "image/png")
        self.assertRegex(
            placeholder_response.headers.get("Content-Disposition", ""),
            r"placeholder\.png",
        )

        no_token_response = self.url_open(
            f"/mail/avatar/mail.message/{mail_record.id}/author_avatar/50x50"
        )
        self.assertEqual(no_token_response.status_code, 200)
        self.assertEqual(no_token_response.headers.get("Content-Type"), "image/png")
        self.assertRegex(
            no_token_response.headers.get("Content-Disposition", ""),
            r"placeholder\.png",
        )

    def test_portal_avatar_with_hash_pid(self):
        self.authenticate(None, None)
        post_url = f"{self.record_portal.get_base_url()}/mail/message/post"
        pid = self.partner_2.id
        _hash = self.record_portal._sign_token(pid)
        res = self.url_open(
            url=post_url,
            json={
                "params": {
                    "thread_model": self.record_portal._name,
                    "thread_id": self.record_portal.id,
                    "post_data": {"body": "Test"},
                    "hash": _hash,
                    "pid": pid,
                },
            },
        )
        res.raise_for_status()
        self.assertNotIn("error", res.json())
        message = self.record_portal.message_ids[0]
        formatted_message = message.portal_message_format(
            options={"hash": _hash, "pid": pid}
        )[0]
        self.assertEqual(
            formatted_message.get("author_avatar_url"),
            f"/mail/avatar/mail.message/{message.id}/author_avatar/50x50?_hash={_hash}&pid={pid}",
        )
        response = self.url_open(
            f"/mail/avatar/mail.message/{message.id}/author_avatar/50x50?_hash={_hash}&pid={pid}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Content-Type"), "image/svg+xml; charset=utf-8"
        )
        self.assertRegex(
            response.headers.get("Content-Disposition", ""),
            r"mail_message-\d+-author_avatar\.svg",
        )

        placeholder_response = self.url_open(
            f"/mail/avatar/mail.message/{message.id}/author_avatar/50x50?_hash={_hash + 'a'}&pid={pid}"
        )
        self.assertEqual(placeholder_response.status_code, 200)
        self.assertEqual(placeholder_response.headers.get("Content-Type"), "image/png")
        self.assertRegex(
            placeholder_response.headers.get("Content-Disposition", ""),
            r"placeholder\.png",
        )

    def test_portal_share_comment(self):
        self.authenticate(None, None)
        post_url = f"{self.record_portal.get_base_url()}/mail/message/post"

        self.url_open(
            url=post_url,
            json={
                "params": {
                    "thread_model": self.record_portal._name,
                    "thread_id": self.record_portal.id,
                    "post_data": {"body": "Test"},
                    "token": self.record_portal.access_token,
                    "hash": self.record_portal._sign_token(self.partner_2.id),
                    "pid": self.partner_2.id,
                },
            },
        )
        messages = self.record_portal.message_ids.filtered(
            lambda msg: msg.author_id == self.partner_2
        )

        self.assertIn("Test", messages[0].body)


@tagged("-at_install", "post_install", "portal", "mail_controller")
class TestPortalFlow(MailCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create(
            {
                "country_id": cls.env.ref("base.fr").id,
                "email": "mdelvaux34@example.com",
                "lang": "en_US",
                "name": "Mathias Delvaux",
                "phone_ids": [
                    Command.create({"number": "+33353011823", "type": "landline"})
                ],
            }
        )
        cls.record_portal = cls.env["mail.test.portal"].create(
            {
                "name": "Test Portal Record",
                "partner_id": cls.customer.id,
                "user_id": cls.user_admin.id,
            }
        )
        cls.record_internal = cls.env["mail.test.track"].create(
            {
                "name": "Test Internal Record",
            }
        )
        cls.record_read = cls.env["mail.test.simple"].create(
            {
                "name": "Test Readable Record",
            }
        )
        cls.record_public_act_url = cls.env[
            "mail.test.portal.public.access.action"
        ].create(
            {
                "name": "Public ActUrl",
            }
        )

        cls.mail_template = cls.env["mail.template"].create(
            {
                "auto_delete": True,
                "body_html": '<p>Hello <t t-out="object.partner_id.name"/>, your quotation is ready for review.</p>',
                "email_from": "{{ (object.user_id.email_formatted or user.email_formatted) }}",
                "model_id": cls.env.ref("test_mail_full.model_mail_test_portal").id,
                "name": "Quotation template",
                "partner_to": "{{ object.partner_id.id }}",
                "subject": 'Your quotation "{{ object.name }}"',
            }
        )
        cls._create_portal_user()

        def patched_generate_signup_token(self, *_, **__):
            self.check_singleton()
            return str([self.id, self._get_login_date(), self.signup_type])

        cls.classPatch(
            ResPartner, "_generate_signup_token", patched_generate_signup_token
        )

        base_url = cls.record_portal.get_base_url()
        cls.test_base_url = base_url

        cls.record_internal_url_base = f"{base_url}/mail/view?model={cls.record_internal._name}&res_id={cls.record_internal.id}"
        cls.record_portal_url_base = f"{base_url}/mail/view?model={cls.record_portal._name}&res_id={cls.record_portal.id}"
        cls.record_read_url_base = f"{base_url}/mail/view?model={cls.record_read._name}&res_id={cls.record_read.id}"
        cls.record_public_act_url_base = f"{base_url}/mail/view?model={cls.record_public_act_url._name}&res_id={cls.record_public_act_url.id}"

        max_internal_id = (
            cls.env["mail.test.track"].search([], order="id desc", limit=1).id
        )
        max_portal_id = (
            cls.env["mail.test.portal"].search([], order="id desc", limit=1).id
        )
        max_read_id = (
            cls.env["mail.test.simple"].search([], order="id desc", limit=1).id
        )
        max_public_act_url_id = (
            cls.env["mail.test.portal.public.access.action"]
            .search([], order="id desc", limit=1)
            .id
        )
        cls.record_internal_url_no_exists = f"{base_url}/mail/view?model={cls.record_internal._name}&res_id={max_internal_id + 1}"
        cls.record_portal_url_no_exists = f"{base_url}/mail/view?model={cls.record_portal._name}&res_id={max_portal_id + 1}"
        cls.record_read_url_no_exists = f"{base_url}/mail/view?model={cls.record_read._name}&res_id={max_read_id + 1}"
        cls.record_public_act_url_url_no_exists = f"{base_url}/mail/view?model={cls.record_public_act_url._name}&res_id={max_public_act_url_id + 1}"

        cls.record_url_no_model = f"{cls.record_portal.get_base_url()}/mail/view?model=this.should.not.exists&res_id=1"

        for (
            group_name,
            group_func,
            group_data,
        ) in cls.record_portal.sudo()._notify_get_recipients_groups(
            cls.env["mail.message"], False
        ):
            if group_name == "portal_customer" and group_func(cls.customer):
                cls.record_portal_url_auth = group_data["button_access"]["url"]
                break
        else:
            raise AssertionError("Record access URL not found")
        parsed_url = urlsplit(cls.record_portal_url_auth)
        query_params = dict(parse_qsl(parsed_url.query))
        cls.record_portal_hash = query_params["hash"]
        cls.record_portal_url_auth_wrong_token = urlunsplit(
            parsed_url._replace(
                query=urlencode(
                    sorted(
                        {
                            **query_params,
                            "access_token": query_params["access_token"].translate(
                                str.maketrans("0123456789abcdef", "9876543210fedcba")
                            ),
                        }.items()
                    )
                )
            )
        )

        cls.portal_web_url = f"{base_url}/my/test_portal/{cls.record_portal.id}"
        cls.portal_web_url_with_token = f"{base_url}/my/test_portal/{cls.record_portal.id}?{urlencode(sorted({'access_token': cls.record_portal.access_token, 'pid': cls.customer.id, 'hash': cls.record_portal_hash}.items()))}"
        cls.public_act_url_share = (
            f"{base_url}/test_portal/public_type/{cls.record_public_act_url.id}"
        )
        cls.internal_backend_local_url = (
            f"/odoo/{cls.record_internal._name}/{cls.record_internal.id}"
        )
        cls.portal_backend_local_url = (
            f"/odoo/{cls.record_portal._name}/{cls.record_portal.id}"
        )
        cls.read_backend_local_url = (
            f"/odoo/{cls.record_read._name}/{cls.record_read.id}"
        )
        cls.public_act_url_backend_local_url = (
            f"/odoo/{cls.record_public_act_url._name}/{cls.record_public_act_url.id}"
        )
        cls.discuss_local_url = "/odoo/action-mail.action_discuss"

    def test_assert_initial_data(self):
        self.record_internal.with_user(self.user_employee).check_access("read")
        self.record_portal.with_user(self.user_employee).check_access("read")
        self.record_read.with_user(self.user_employee).check_access("read")

        with self.assertRaises(AccessError):
            self.record_internal.with_user(self.user_portal).check_access("read")
        with self.assertRaises(AccessError):
            self.record_portal.with_user(self.user_portal).check_access("read")
        self.record_read.with_user(self.user_portal).check_access("read")

        self.assertNotEqual(
            self.record_portal_url_auth, self.record_portal_url_auth_wrong_token
        )
        url_params = []
        for url in (
            self.record_portal_url_auth,
            self.record_portal_url_auth_wrong_token,
        ):
            with self.subTest(url=url):
                parsed = urlsplit(url)
                self.assertEqual(parsed.path, "/mail/view")
                params = dict(parse_qsl(parsed.query))
                url_params.append(params)
                self.assertEqual(params.get("model"), "mail.test.portal")
                self.assertEqual(int(params.get("res_id")), self.record_portal.id)
                self.assertTrue(params.get("access_token"))
        self.assertNotEqual(
            url_params[0]["access_token"], url_params[1]["access_token"]
        )
        self.assertEqual(
            {k: v for k, v in url_params[0].items() if k != "access_token"},
            {k: v for k, v in url_params[1].items() if k != "access_token"},
            "URLs should be the same, except for access token",
        )

    @users("employee")
    def test_employee_access(self):
        self.authenticate(self.env.user.login, self.env.user.login)
        for url_name, url, exp_url in [
            (
                "Internal record mail/view",
                self.record_internal_url_base,
                self.internal_backend_local_url,
            ),
            (
                "Portal record mail/view",
                self.record_portal_url_base,
                self.portal_backend_local_url,
            ),
            (
                "Portal readable record mail/view",
                self.record_read_url_base,
                self.read_backend_local_url,
            ),
            (
                "Public with act_url",
                self.record_public_act_url_base,
                self.public_act_url_backend_local_url,
            ),
            (
                "Portal record with token",
                self.record_portal_url_auth,
                self.portal_backend_local_url,
            ),
            (
                "Portal record with wrong token",
                self.record_portal_url_auth_wrong_token,
                self.portal_backend_local_url,
            ),
            (
                "Not existing record (internal)",
                self.record_internal_url_no_exists,
                self.discuss_local_url,
            ),
            (
                "Not existing record (portal enabled)",
                self.record_portal_url_no_exists,
                self.discuss_local_url,
            ),
            ("Not existign model", self.record_url_no_model, self.discuss_local_url),
        ]:
            with self.subTest(name=url_name, url=url):
                res = self.url_open(url)
                self.assertEqual(res.status_code, 200)
                self.assertURLEqual(res.url, exp_url)

    @mute_logger("odoo.service.http.access")
    @users("portal_test")
    def test_portal_access_logged(self):
        my_url = f"{self.test_base_url}/my"

        self.authenticate(self.env.user.login, self.env.user.login)
        for url_name, url, exp_url in [
            (
                "No access (portal enabled), token",
                self.record_portal_url_auth,
                self.portal_web_url_with_token,
            ),
            (
                "No access (portal enabled), invalid token",
                self.record_portal_url_auth_wrong_token,
                my_url,
            ),
            (
                "Access record (no customer portal)",
                self.record_read_url_base,
                f"{self.test_base_url}/my?{urlencode({'subpath': f'{self.record_read._name}/{self.record_read.id}'})}",
            ),
            (
                "No access record (internal)",
                self.record_internal_url_base,
                my_url,
            ),
            (
                "No access record (portal enabled)",
                self.record_portal_url_base,
                my_url,
            ),
            (
                "Public with act_url -> frontend url",
                self.record_public_act_url_base,
                self.public_act_url_share,
            ),
            (
                "Not existing record (internal)",
                self.record_internal_url_no_exists,
                my_url,
            ),
            (
                "Not existing record (portal enabled)",
                self.record_portal_url_no_exists,
                my_url,
            ),
            (
                "Not existing model",
                self.record_url_no_model,
                my_url,
            ),
        ]:
            with self.subTest(name=url_name, url=url):
                res = self.url_open(url)
                self.assertEqual(res.status_code, 200)
                self.assertURLEqual(res.url, exp_url)

    @mute_logger("odoo.service.http.access")
    def test_portal_access_not_logged(self):
        self.authenticate(None, None)
        login_url = f"{self.test_base_url}/web/login"

        for url_name, url, exp_url in [
            (
                "No access (portal enabled), token",
                self.record_portal_url_auth,
                self.portal_web_url_with_token,
            ),
            (
                "No access (portal enabled), invalid token",
                self.record_portal_url_auth_wrong_token,
                f"{login_url}?{urlencode({'redirect': self.record_portal_url_auth_wrong_token.replace(self.test_base_url, '')})}",
            ),
            (
                "No access record (internal)",
                self.record_internal_url_base,
                f"{login_url}?{urlencode({'redirect': self.record_internal_url_base.replace(self.test_base_url, '')})}",
            ),
            (
                "No access record (portal enabled)",
                self.record_portal_url_base,
                f"{login_url}?{urlencode({'redirect': self.record_portal_url_base.replace(self.test_base_url, '')})}",
            ),
            (
                "No access record (portal can read, no customer portal)",
                self.record_read_url_base,
                f"{login_url}?{urlencode({'redirect': self.record_read_url_base.replace(self.test_base_url, '')})}",
            ),
            (
                "Public with act_url -> frontend url",
                self.record_public_act_url_base,
                self.public_act_url_share,
            ),
            (
                "Not existing record (internal)",
                self.record_internal_url_no_exists,
                f"{login_url}?{urlencode({'redirect': self.record_internal_url_no_exists.replace(self.test_base_url, '')})}",
            ),
            (
                "Not existing record (portal enabled)",
                self.record_portal_url_no_exists,
                f"{login_url}?{urlencode({'redirect': self.record_portal_url_no_exists.replace(self.test_base_url, '')})}",
            ),
            (
                "Not existing model",
                self.record_url_no_model,
                f"{login_url}?{urlencode({'redirect': self.record_url_no_model.replace(self.test_base_url, '')})}",
            ),
        ]:
            with self.subTest(name=url_name, url=url):
                res = self.url_open(url)
                self.assertEqual(res.status_code, 200)
                self.assertURLEqual(res.url, exp_url)

    def test_redirect_to_records_norecord(self):
        for model, res_id in [
            (False, self.record_portal.id),
            ("", self.record_portal.id),
            (self.record_portal._name, False),
            (self.record_portal._name, ""),
            (False, False),
            ("wrong.model", self.record_portal.id),
            (self.record_portal._name, -4),
        ]:
            response = self.url_open(
                "/mail/view?model=%s&res_id=%s" % (model, res_id), timeout=15
            )
            path = urlsplit(response.url).path
            self.assertEqual(
                path, "/web/login", "Failed with %s - %s" % (model, res_id)
            )

    def assert_URL(
        self, url, expected_path, expected_fragment_params=None, expected_query=None
    ):
        parsed_url = urlsplit(url)
        fragment_params = dict(parse_qsl(parsed_url.fragment))
        self.assertEqual(parsed_url.path, expected_path)
        if expected_fragment_params:
            for key, expected_value in expected_fragment_params.items():
                self.assertEqual(
                    fragment_params.get(key),
                    expected_value,
                    f'Expected: "{key}={expected_value}" (for path: {expected_path})',
                )
        if expected_query:
            self.assertEqual(
                expected_query,
                parsed_url.query,
                f'Expected: query="{expected_query}" (for path: {expected_path})',
            )

    @users("employee")
    def test_send_message_to_customer(self):
        composer = (
            self.env["wizard.mail.message.send"]
            .with_context(
                self._get_mail_composer_web_context(
                    self.record_portal,
                    default_email_layout_xmlid="mail.mail_notification_layout_with_responsible_signature",
                )
            )
            .create(
                {
                    "body": "<p>Hello Mathias Delvaux, your quotation is ready for review.</p>",
                    "partner_ids": self.customer.ids,
                    "subject": 'Your Quotation "a white table"',
                }
            )
        )

        with self.mock_mail_gateway(mail_unlink_sent=True):
            composer._action_send_mail()

        self.assertEqual(len(self._mails), 1)
        self.assertIn(
            f'"{html_escape(self.record_portal_url_auth)}"', self._mails[0].get("body")
        )
        self.assertEqual(
            'Your Quotation "a white table"', self._mails[0].get("subject")
        )
        self.assertIn("Hello Mathias Delvaux", self._mails[0].get("body"))

    @users("employee")
    def test_send_message_to_customer_using_template(self):
        composer = (
            self.env["wizard.mail.message.send"]
            .with_context(
                self._get_mail_composer_web_context(
                    self.record_portal,
                    default_email_layout_xmlid="mail.mail_notification_layout_with_responsible_signature",
                    default_template_id=self.mail_template.id,
                )
            )
            .create({})
        )

        with self.mock_mail_gateway(mail_unlink_sent=True):
            composer._action_send_mail()

        self.assertEqual(len(self._mails), 1)
        self.assertIn(
            f'"{html_escape(self.record_portal_url_auth)}"', self._mails[0].get("body")
        )
        self.assertEqual(
            f'Your quotation "{self.record_portal.name}"', self._mails[0].get("subject")
        )


@tagged("portal")
class TestPortalMixin(TestPortal):
    @users("employee")
    def test_portal_mixin(self):
        customer = self.partner_1.with_env(self.env)
        record_portal = self.env["mail.test.portal"].create(
            {
                "partner_id": customer.id,
                "name": "Test Portal Record",
            }
        )

        self.assertFalse(record_portal.access_token)
        self.assertEqual(
            record_portal.access_url, "/my/test_portal/%s" % record_portal.id
        )

        record_portal._portal_get_or_create_token()
        self.assertTrue(record_portal.access_token)


@tagged("portal", "post_install", "-at_install")
class TestPortalAttachmentRemoval(HttpCase):
    def _remove(self, attachment, access_token):
        return self.url_open(
            "/portal/attachment/remove",
            json={
                "params": {"attachment_id": attachment.id, "access_token": access_token}
            },
        ).json()

    def test_a_visitor_removes_a_pending_upload_with_its_own_token(self):
        attachment = self.env["ir.attachment"].create(
            {"name": "upload.txt", "res_model": "wizard.mail.message.send", "res_id": 0}
        )
        attachment.generate_access_token()
        self.authenticate(None, None)
        refused = self._remove(attachment, "not-the-token")
        self.assertIn("error", refused)
        self.assertTrue(attachment.exists())
        self.assertNotIn("error", self._remove(attachment, attachment.access_token))
        self.assertFalse(attachment.exists())

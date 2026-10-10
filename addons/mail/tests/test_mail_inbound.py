import base64
import os
from unittest.mock import patch

import psycopg
from cryptography.fernet import Fernet

from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import BaseCase, HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.mail.tools.inbound_delivery import InboundDelivery


def _message(
    message_id: str,
    to: str = "someone@elsewhere.example",
    charset: str = "utf-8",
    body: bytes = b"hello",
) -> bytes:
    return (
        b"From: Customer <customer@example.org>\r\n"
        b"To: " + to.encode() + b"\r\n"
        b"Subject: Order 42\r\n"
        b"Message-Id: <" + message_id.encode() + b">\r\n"
        b"Content-Type: text/plain; charset=" + charset.encode() + b"\r\n"
        b"Content-Transfer-Encoding: 8bit\r\n"
        b"\r\n" + body + b"\r\n"
    )


def _envelope(message: bytes, recipients: list[str], sender: str = "") -> dict:
    return {
        "sender": sender,
        "recipients": recipients,
        "message": base64.b64encode(message).decode(),
    }


@tagged("post_install", "-at_install")
class TestInboundDelivery(BaseCase):
    def test_the_envelope_is_stamped_as_a_final_delivery(self):
        delivery = InboundDelivery.from_envelope(
            _envelope(_message("a@x"), ["Orders@Example.COM"], "bounce@example.org")
        )
        stamped = delivery.stamped()
        self.assertTrue(
            stamped.startswith(
                b"Return-Path: <bounce@example.org>\r\n"
                b"Delivered-To: orders@example.com\r\n"
            ),
            stamped[:120],
        )
        self.assertTrue(stamped.endswith(_message("a@x")), "the message is untouched")

    def test_the_mta_s_null_sender_name_is_the_null_sender(self):
        delivery = InboundDelivery.from_envelope(
            _envelope(_message("daemon@x"), ["a@b.c"], "MAILER-DAEMON")
        )
        self.assertTrue(delivery.stamped().startswith(b"Return-Path: <>"))

    def test_the_null_sender_is_an_empty_return_path(self):
        delivery = InboundDelivery.from_envelope(_envelope(_message("b@x"), ["a@b.c"]))
        self.assertTrue(delivery.stamped().startswith(b"Return-Path: <>\r\n"))

    def test_a_bare_newline_message_keeps_its_line_endings(self):
        raw = _message("c@x").replace(b"\r\n", b"\n")
        stamped = InboundDelivery.from_envelope(_envelope(raw, ["a@b.c"])).stamped()
        self.assertNotIn(b"\r\n", stamped)

    def test_a_malformed_envelope_is_refused(self):
        good = _envelope(_message("d@x"), ["a@b.c"])
        for label, envelope in [
            ("no recipients", {**good, "recipients": []}),
            ("recipients not a list", {**good, "recipients": "a@b.c"}),
            ("not an address", {**good, "recipients": ["nobody"]}),
            ("header injection", {**good, "sender": "a@b.c>\r\nBcc: x@y.z"}),
            ("not base64", {**good, "message": "@@@"}),
            ("empty message", {**good, "message": base64.b64encode(b" ").decode()}),
            ("no message", {k: v for k, v in good.items() if k != "message"}),
        ]:
            with self.subTest(label), self.assertRaises(ValueError):
                InboundDelivery.from_envelope(envelope)


@tagged("post_install", "-at_install")
class TestMailGatewayRecipient(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alias_domain = cls.env["mail.alias.domain"].create(
            {
                "name": "rcpt.example.com",
                "bounce_alias": "bounce-rcpt",
                "catchall_alias": "catchall-rcpt",
            }
        )

    def _recipients(self) -> dict[str, str]:
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT address, kind FROM mail_gateway_recipient WHERE alias_domain_id = %s",
            [self.alias_domain.id],
        )
        return dict(self.env.cr.fetchall())

    def test_the_view_lists_what_the_gateway_answers(self):
        before = self._recipients()
        self.assertEqual(before["bounce-rcpt@rcpt.example.com"], "bounce")
        self.assertEqual(before["catchall-rcpt@rcpt.example.com"], "catchall")
        alias = self.env["mail.alias"].create(
            {
                "alias_name": "orders",
                "alias_domain_id": self.alias_domain.id,
                "alias_model_id": self.env.ref("base.model_res_partner").id,
            }
        )
        self.assertEqual(
            self._recipients(), {**before, "orders@rcpt.example.com": "alias"}
        )
        alias.unlink()
        self.assertEqual(self._recipients(), before)

    def test_a_local_part_alias_is_answered_on_every_domain(self):
        other = self.env["mail.alias.domain"].create(
            {
                "name": "other-rcpt.example.com",
                "bounce_alias": "bounce-other",
                "catchall_alias": "catchall-other",
            }
        )
        before = self._recipients()
        self.env["mail.alias"].create(
            {
                "alias_name": "helpdesk",
                "alias_domain_id": other.id,
                "alias_incoming_local": True,
                "alias_model_id": self.env.ref("base.model_res_partner").id,
            }
        )
        self.assertEqual(
            self._recipients(), {**before, "helpdesk@rcpt.example.com": "alias"}
        )

    def test_a_renamed_domain_moves_every_address(self):
        before = self._recipients()
        self.alias_domain.name = "moved.example.com"
        self.assertEqual(
            self._recipients(),
            {
                address.replace("@rcpt.example.com", "@moved.example.com"): kind
                for address, kind in before.items()
            },
        )

    def test_the_columns_are_the_mta_contract(self):
        self.env.cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'mail_gateway_recipient' ORDER BY ordinal_position
            """
        )
        self.assertEqual(
            [name for (name,) in self.env.cr.fetchall()],
            ["address", "kind", "alias_domain_id"],
            "the MTA's lookup query names these columns; changing them is a "
            "deployment change, not a refactor",
        )


@tagged("post_install", "-at_install")
class TestMailInbound(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        patcher = patch.dict(
            os.environ,
            {
                "ODOO_API_ENCRYPTION_KEY": os.environ.get("ODOO_API_ENCRYPTION_KEY")
                or Fernet.generate_key().decode()
            },
            clear=False,
        )
        cls.startClassPatcher(patcher)
        cls.env["credential.credential"]._invalidate_key_version_cache()
        cls.addClassCleanup(
            cls.env["credential.credential"]._invalidate_key_version_cache
        )
        cls.alias_domain = cls.env["mail.alias.domain"].create(
            {
                "name": "inbound.example.com",
                "bounce_alias": "bounce-inbound",
                "catchall_alias": "catchall-inbound",
            }
        )
        cls.channel = cls.env["discuss.channel"].create(
            {"name": "Orders", "channel_type": "channel"}
        )
        cls.env["mail.alias"].create(
            {
                "alias_name": "orders",
                "alias_domain_id": cls.alias_domain.id,
                "alias_model_id": cls.env.ref("mail.model_discuss_channel").id,
                "alias_force_thread_id": cls.channel.id,
            }
        )
        cls.server = cls.env["fetchmail.server"].create(
            {"name": "Edge", "server_type": "local"}
        )

    def setUp(self):
        super().setUp()
        with self.sync_env_with_side_cursors():
            action = self.server.action_issue_inbound_token()
        self.token = action["params"]["message"].split("\n", 1)[0]

    def _post(self, envelope, token=None, server=None):
        return self.url_open(
            f"/mail/inbound/{(server or self.server).id}",
            data=json_dumps(envelope),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token or self.token}",
            },
        )

    def _channel_messages(self, message_id):
        self.env.invalidate_all()
        return self.env["mail.message"].search(
            [
                ("model", "=", "discuss.channel"),
                ("res_id", "=", self.channel.id),
                ("message_id", "=", f"<{message_id}>"),
            ]
        )

    def _exchanges(self):
        self.env.invalidate_all()
        receiver = self.server._get_inbound_receiver()
        return self.env["integration.exchange"].search(
            [("channel_id", "=", f"integration.receiver,{receiver.id}")]
        )

    def test_a_message_reaches_its_alias(self):
        response = self._post(
            _envelope(
                _message("one@x", to="orders@inbound.example.com"),
                ["orders@inbound.example.com"],
            )
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"delivered": True})
        self.assertEqual(len(self._channel_messages("one@x")), 1)

    def test_a_bcc_recipient_is_routed_by_the_envelope(self):
        response = self._post(
            _envelope(
                _message("bcc@x", to="someone@elsewhere.example"),
                ["orders@inbound.example.com"],
            )
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            len(self._channel_messages("bcc@x")),
            1,
            "no header names the alias: only the envelope does",
        )

    def test_an_eight_bit_message_arrives_intact(self):
        response = self._post(
            _envelope(
                _message(
                    "latin@x",
                    to="orders@inbound.example.com",
                    charset="iso-8859-1",
                    body="señor café".encode("latin-1"),
                ),
                ["orders@inbound.example.com"],
            )
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("señor café", str(self._channel_messages("latin@x").body))

    def test_a_resent_envelope_is_delivered_once(self):
        envelope = _envelope(
            _message("twice@x", to="orders@inbound.example.com"),
            ["orders@inbound.example.com"],
        )
        self.assertEqual(self._post(envelope).status_code, 200)
        again = self._post(envelope)
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(again.json()["error"], "duplicate_event")
        self.assertEqual(len(self._channel_messages("twice@x")), 1)

    @mute_logger("odoo.addons.mail.models.mixin_mail_gateway")
    def test_an_unroutable_message_is_refused_without_a_trace(self):
        response = self._post(
            _envelope(
                _message("lost@x", to="nobody@inbound.example.com"),
                ["nobody@inbound.example.com"],
            )
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["error"], "no_route")
        self.env.invalidate_all()
        self.assertFalse(
            self.env["mail.gateway.receipt"].search([("message_id", "=", "<lost@x>")]),
            "a claimed Message-Id would drop the same message once an alias exists",
        )

    @mute_logger("odoo.addons.mail.models.mixin_mail_gateway")
    def test_a_server_whose_fallback_takes_no_document_defers_the_message(self):
        self.server.object_id = self.env.ref("base.model_res_country")
        response = self._post(
            _envelope(
                _message("unusable@x", to="nobody@inbound.example.com"),
                ["nobody@inbound.example.com"],
            )
        )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"], "route_misconfigured")
        self.env.invalidate_all()
        self.assertFalse(
            self.env["mail.gateway.receipt"].search(
                [("message_id", "=", "<unusable@x>")]
            ),
            "a claimed Message-Id would drop the retried message as a duplicate",
        )

    @mute_logger("odoo.addons.mail.models.mixin_mail_gateway")
    def test_a_bounce_of_an_unknown_message_is_taken_not_retried(self):
        bounce = (
            b"From: MAILER-DAEMON@relay.example.org\r\n"
            b"To: bounce-inbound@inbound.example.com\r\n"
            b"Subject: Undelivered Mail Returned to Sender\r\n"
            b"Message-Id: <bounce-unknown@x>\r\n"
            b"In-Reply-To: <never-sent@inbound.example.com>\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"gone\r\n"
        )
        response = self._post(_envelope(bounce, ["bounce-inbound@inbound.example.com"]))
        self.assertLess(response.status_code, 500, response.text)

    def test_the_message_content_is_not_logged(self):
        self._post(
            _envelope(
                _message("private@x", to="orders@inbound.example.com"),
                ["orders@inbound.example.com"],
            )
        )
        exchanges = self._exchanges()
        self.assertTrue(exchanges)
        self.assertFalse(any(exchanges.mapped("request_payload")))

    def test_a_malformed_envelope_is_a_bad_request(self):
        response = self._post({"recipients": ["orders@inbound.example.com"]})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["error"], "invalid_envelope")

    def test_a_caller_without_the_token_is_refused(self):
        envelope = _envelope(
            _message("forged@x", to="orders@inbound.example.com"),
            ["orders@inbound.example.com"],
        )
        self.assertIn(self._post(envelope, token="wrong").status_code, (401, 403))
        self.assertFalse(self._channel_messages("forged@x"))

    def test_a_reissued_token_retires_the_previous_one(self):
        previous = self.token
        with self.sync_env_with_side_cursors():
            action = self.server.action_issue_inbound_token()
        current = action["params"]["message"].split("\n", 1)[0]
        envelope = _envelope(
            _message("rotated@x", to="orders@inbound.example.com"),
            ["orders@inbound.example.com"],
        )
        self.assertIn(self._post(envelope, token=previous).status_code, (401, 403))
        self.assertEqual(self._post(envelope, token=current).status_code, 200)

    def test_only_a_local_server_receives(self):
        imap = self.env["fetchmail.server"].create(
            {
                "name": "Mailbox",
                "server_type": "imap",
                "server": "imap.example.com",
                "user": "u",
            }
        )
        envelope = _envelope(_message("imap@x"), ["orders@inbound.example.com"])
        self.assertEqual(self._post(envelope, server=imap).status_code, 404)
        with self.assertRaises(UserError):
            imap.action_issue_inbound_token()

    def test_the_setup_text_names_this_server_s_url(self):
        configuration = self.server.configuration
        self.assertIn(f"/mail/inbound/{self.server.id}", configuration)
        self.assertIn("--recipient=${recipient}", configuration)
        self.assertIn("mail_gateway_recipient", configuration)

    def test_mail_is_processed_as_the_polling_gateway_would(self):
        self.env["mail.alias"].create(
            {
                "alias_name": "contacts",
                "alias_domain_id": self.alias_domain.id,
                "alias_model_id": self.env.ref("base.model_res_partner").id,
            }
        )
        message = _message("identity@x", to="contacts@inbound.example.com").replace(
            b"Subject: Order 42", b"Subject: Identity Probe"
        )
        response = self._post(_envelope(message, ["contacts@inbound.example.com"]))
        self.assertEqual(response.status_code, 200, response.text)
        self.env.invalidate_all()
        created = self.env["res.partner"].search([("name", "=", "Identity Probe")])
        self.assertEqual(
            created.create_uid,
            self.env.ref("mail.ir_cron_mail_gateway_action").user_id,
            "a pushed message is processed by the identity a polled one is",
        )

    def test_a_bcc_recipient_is_not_disclosed_to_the_other_routes(self):
        self.env["mail.alias"].create(
            {
                "alias_name": "audit",
                "alias_domain_id": self.alias_domain.id,
                "alias_model_id": self.env.ref("base.model_res_partner").id,
            }
        )
        auditor = self.env["res.partner"].create(
            {"name": "Auditor", "email": "audit@inbound.example.com"}
        )
        response = self._post(
            _envelope(
                _message("quiet-bcc@x", to="orders@inbound.example.com"),
                ["orders@inbound.example.com", "audit@inbound.example.com"],
            )
        )
        self.assertEqual(response.status_code, 200, response.text)
        posted = self._channel_messages("quiet-bcc@x")
        self.assertEqual(len(posted), 1)
        self.assertNotIn(
            auditor,
            posted.partner_ids,
            "the orders thread must not learn who else was Bcc'd",
        )

    def test_a_concurrency_failure_is_retried_within_the_delivery(self):
        self.env["mail.alias"].create(
            {
                "alias_name": "retried",
                "alias_domain_id": self.alias_domain.id,
                "alias_model_id": self.env.ref("base.model_res_partner").id,
            }
        )
        Partner = type(self.env["res.partner"])
        original = Partner.message_new
        attempts = []

        def message_new(records, msg_dict, custom_values=None):
            attempts.append(1)
            if len(attempts) == 1:
                raise psycopg.errors.SerializationFailure("concurrent update")
            return original(records, msg_dict, custom_values)

        message = _message("retried@x", to="retried@inbound.example.com").replace(
            b"Subject: Order 42", b"Subject: Retried Probe"
        )
        with patch.object(Partner, "message_new", message_new):
            response = self._post(_envelope(message, ["retried@inbound.example.com"]))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(attempts), 2, "the request replayed once")
        self.env.invalidate_all()
        self.assertEqual(
            self.env["res.partner"].search_count([("name", "=", "Retried Probe")]), 1
        )


@tagged("post_install", "-at_install")
class TestGatewayRetryableFailure(TransactionCase):
    def test_a_retryable_failure_neither_bounces_nor_blames_the_alias(self):
        domain = self.env["mail.alias.domain"].create(
            {"name": "retry.example.com", "bounce_alias": "bounce-retry"}
        )
        alias = self.env["mail.alias"].create(
            {
                "alias_name": "retry",
                "alias_domain_id": domain.id,
                "alias_model_id": self.env.ref("base.model_res_partner").id,
            }
        )
        self.env.company.alias_domain_id = domain
        Partner = type(self.env["res.partner"])
        bounces_before = self.env["mail.mail"].search_count([])
        with (
            self.sync_env_with_side_cursors(),
            patch.object(
                Partner,
                "message_new",
                side_effect=psycopg.errors.SerializationFailure("concurrent update"),
            ),
        ):
            try:
                self.env["mixin.mail.thread"].message_process(
                    False, _message("retry@x", to="retry@retry.example.com")
                )
            except psycopg.errors.SerializationFailure:
                pass
            else:
                self.fail("the retryable failure must reach the transaction")
        self.env.invalidate_all()
        self.assertNotEqual(
            alias.alias_status,
            "invalid",
            "the transaction is retried; nothing is wrong with the alias",
        )
        self.assertEqual(
            self.env["mail.mail"].search_count([]),
            bounces_before,
            "no bounce for a message the retry will deliver",
        )

from unittest.mock import patch
from uuid import uuid4

from psycopg.errors import LockNotAvailable, SerializationFailure
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from odoo import SUPERUSER_ID, api
from odoo.db import db_connect
from odoo.http.core import _request_stack
from odoo.tests import BaseCase, tagged
from odoo.tests.common import request_stand_in
from odoo.tests.utils import get_db_name
from odoo.tools import SQL

from odoo.addons.integration.tools.admission import Refused


@tagged("post_install", "-at_install")
class TestAdmissionConcurrency(BaseCase):
    def setUp(self):
        super().setUp()
        self.db = db_connect(get_db_name())
        with self.db.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            user = env["res.users"].create(
                {
                    "name": "Channel race principal",
                    "login": f"channel-race-{uuid4().hex}",
                    "principal_type": "service",
                }
            )
            self.user_id, self.partner_id = user.id, user.partner_id.id
            enrollment = env["device.enrollment"].create(
                {"name": f"Race {uuid4().hex}", "service_user_id": user.id}
            )
            enrollment.action_provision_credential()
            enrollment.action_activate()
            channels = env["device.channel"].create(
                [
                    {
                        "name": "First race channel",
                        "enrollment_id": enrollment.id,
                        "external_identifier": "first",
                        "rate_limit_enabled": False,
                    },
                    {
                        "name": "Second race channel",
                        "enrollment_id": enrollment.id,
                        "external_identifier": "second",
                        "rate_limit_enabled": False,
                    },
                ]
            )
            self.enrollment_id = enrollment.id
            self.channel_ids = channels.ids
            self.credential_id = enrollment.credential_id.id
            self.token = enrollment.credential_id.credential_value
            env.flush_all()
        self.addCleanup(self._cleanup_fixture)

    def _cleanup_fixture(self):
        with self.db.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            current = (
                env["device.enrollment"].browse(self.enrollment_id).credential_id.id
            )
            credential_ids = tuple(
                ident for ident in {self.credential_id, current} if ident
            )
            cr.execute(
                SQL(
                    "DELETE FROM rate_limit_bucket WHERE endpoint_model = %s AND endpoint_id IN %s",
                    "device.channel",
                    tuple(self.channel_ids),
                )
            )
            cr.execute(
                SQL(
                    "DELETE FROM integration_exchange WHERE channel_id IN %s",
                    tuple(f"device.channel,{ident}" for ident in self.channel_ids),
                )
            )
            cr.execute(
                SQL(
                    "DELETE FROM device_transport_event WHERE enrollment_ref = %s",
                    self.enrollment_id,
                )
            )
            cr.execute(
                SQL(
                    "DELETE FROM device_channel WHERE id IN %s", tuple(self.channel_ids)
                )
            )
            cr.execute(
                SQL("DELETE FROM device_enrollment WHERE id = %s", self.enrollment_id)
            )
            cr.execute(
                SQL(
                    "DELETE FROM credential_access_log WHERE credential_id IN %s",
                    credential_ids,
                )
            )
            cr.execute(
                SQL(
                    "DELETE FROM credential_credential WHERE id IN %s",
                    credential_ids,
                )
            )
            env["res.users"].browse(self.user_id).unlink()
            env["res.partner"].browse(self.partner_id).unlink()
            env.flush_all()

    def _channel(self, cr, index=0):
        return api.Environment(cr, SUPERUSER_ID, {})["device.channel"].browse(
            self.channel_ids[index]
        )

    def _decide(self, channel):
        channel._hold_inbound_authority()
        return channel._decide_inbound_request(
            {"Authorization": f"Bearer {self.token}"}
        )

    def _mutate(self, mutation, *, timeout=False):
        with self.db.cursor() as cr:
            if timeout:
                cr.execute("SET LOCAL lock_timeout = '100ms'")
            channel = self._channel(cr)
            mutation(channel)
            channel.env.flush_all()

    def test_committed_revocation_rejects_an_old_snapshot(self):
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            channel = self._channel(cr)
            self.assertEqual(channel.enrollment_id.state, "active")
            self._mutate(lambda channel: channel.enrollment_id.action_revoke())
            self._decide(channel)
        with self.db.cursor() as cr:
            self.assertFalse(self._decide(self._channel(cr))[0])

    def test_revocation_waits_for_an_admitted_transaction(self):
        with self.db.cursor() as cr:
            self.assertTrue(self._decide(self._channel(cr))[0])
            with self.assertRaises(LockNotAvailable):
                self._mutate(
                    lambda channel: channel.enrollment_id.action_revoke(), timeout=True
                )
        self._mutate(lambda channel: channel.enrollment_id.action_revoke())
        with self.db.cursor() as cr:
            self.assertFalse(self._decide(self._channel(cr))[0])

    def test_policy_change_rejects_an_old_snapshot(self):
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            channel = self._channel(cr)
            self.assertTrue(channel.active)
            self._mutate(lambda channel: channel.write({"active": False}))
            self._decide(channel)

    def test_credential_disable_rejects_an_old_snapshot(self):
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            channel = self._channel(cr)
            self.assertTrue(channel.credential_id.active)
            self._mutate(lambda channel: channel.credential_id.write({"active": False}))
            self._decide(channel)

    def test_rotation_rejects_an_old_snapshot_and_old_token(self):
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            channel = self._channel(cr)
            self.assertEqual(channel.credential_id.id, self.credential_id)
            self._mutate(
                lambda channel: channel.enrollment_id.action_provision_credential()
            )
            self._decide(channel)
        with self.db.cursor() as cr:
            self.assertFalse(self._decide(self._channel(cr))[0])

    def test_principal_disable_rejects_an_old_snapshot(self):
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            channel = self._channel(cr)
            self.assertTrue(channel.service_user_id.active)
            self._mutate(
                lambda channel: channel.service_user_id.write({"active": False})
            )
            self._decide(channel)

    def test_distinct_channels_admit_concurrently(self):
        with self.db.cursor() as first, self.db.cursor() as second:
            second.execute("SET LOCAL lock_timeout = '100ms'")
            self.assertTrue(self._decide(self._channel(first))[0])
            self.assertTrue(self._decide(self._channel(second, 1))[0])

    def _admit(self, channel, request_state=None):
        builder = EnvironBuilder(
            path="/device/admission-probe",
            method="POST",
            headers={"Authorization": f"Bearer {self.token}"},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )
        httprequest = Request(builder.get_environ())
        state = request_state if request_state is not None else request_stand_in()
        state.env = channel.env
        state.httprequest = httprequest
        _request_stack.push(state)
        try:
            return channel.admit()
        finally:
            _request_stack.pop()
            httprequest.close()
            builder.close()

    def test_real_admission_holds_authority_after_verdict_cursor_closes(self):
        with self.db.cursor() as cr:
            admission = self._admit(self._channel(cr))
            mutations = {
                "revocation": lambda c: c.enrollment_id.action_revoke(),
                "rotation": lambda c: c.enrollment_id.action_provision_credential(),
                "channel policy": lambda c: c.write({"max_payload_size": 4096}),
                "credential": lambda c: c.credential_id.write({"active": False}),
                "principal": lambda c: c.service_user_id.write({"active": False}),
            }
            for name, mutation in mutations.items():
                with self.subTest(authority=name), self.assertRaises(LockNotAvailable):
                    self._mutate(mutation, timeout=True)
            admission.settle()
        self._mutate(lambda channel: channel.enrollment_id.action_revoke())

    def test_real_admission_rejects_a_stale_request_snapshot(self):
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            channel = self._channel(cr)
            self.assertTrue(channel.active)
            self._mutate(lambda c: c.write({"max_payload_size": 4096}))
            self._admit(channel)

    def test_missing_credential_refusal_survives_request_rollback(self):
        self._mutate(lambda c: c.enrollment_id.action_revoke())
        self._mutate(lambda c: c.enrollment_id.write({"credential_id": False}))
        with self.assertRaises(Refused), self.db.cursor() as cr:
            self._admit(self._channel(cr))
        with self.db.cursor() as cr:
            channel = self._channel(cr)
            refusal = channel.env["integration.exchange"].search(
                [
                    ("channel_id", "=", f"device.channel,{channel.id}"),
                    ("refusal_reason", "=", "inactive_enrollment"),
                ]
            )
            self.assertEqual(len(refusal), 1)

    def _limit_first_channel(self):
        self._mutate(
            lambda c: c.write(
                {
                    "rate_limit_enabled": True,
                    "rate_limit_requests": 1,
                    "rate_limit_window_seconds": 3600,
                }
            )
        )

    def test_transaction_retry_does_not_charge_the_request_twice(self):
        self._limit_first_channel()
        request_state = request_stand_in()
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state)
            raise SerializationFailure("retry after admission")
        with self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state).settle()
        with self.assertRaises(Refused) as refused, self.db.cursor() as cr:
            self._admit(self._channel(cr))
        self.assertEqual(refused.exception.status, 429)

    def test_rolled_back_verdict_does_not_grant_an_allowance(self):
        self._limit_first_channel()
        request_state = request_stand_in()
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            channel = self._channel(cr)
            with patch.object(
                type(channel),
                "_record_inbound_verdict",
                side_effect=SerializationFailure("verdict did not commit"),
            ):
                self._admit(channel, request_state)
        with self.db.cursor() as cr:
            self._admit(self._channel(cr)).settle()
        with self.assertRaises(Refused) as refused, self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state)
        self.assertEqual(refused.exception.status, 429)

    def test_replayed_allowance_does_not_bypass_revocation(self):
        self._limit_first_channel()
        request_state = request_stand_in()
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state)
            raise SerializationFailure("retry after admission")
        self._mutate(lambda c: c.enrollment_id.action_revoke())
        with self.assertRaises(Refused) as refused, self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state)
        self.assertEqual(refused.exception.error_code, "inactive_enrollment")

    def test_policy_change_requires_a_new_allowance(self):
        self._limit_first_channel()
        request_state = request_stand_in()
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state)
            raise SerializationFailure("retry after admission")
        self._mutate(lambda c: c.write({"rate_limit_window_seconds": 7200}))
        with self.assertRaises(Refused) as refused, self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state)
        self.assertEqual(refused.exception.error_code, "rate_limit_exceeded")

    def test_replay_reuses_the_caller_allowance(self):
        self._limit_first_channel()
        with self.db.cursor() as cr:
            channel = self._channel(cr)
            for _ in range(9):
                self.assertTrue(channel._consume_caller_allowance("127.0.0.1"))
        request_state = request_stand_in()
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state)
            raise SerializationFailure("retry after admission")
        with self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state).settle()
        with self.assertRaises(Refused) as refused, self.db.cursor() as cr:
            self._admit(self._channel(cr))
        self.assertEqual(refused.exception.error_code, "caller_limited")

    def test_retry_does_not_duplicate_its_own_rolled_back_attempt(self):
        self._mutate(lambda c: c.write({"duplicate_detection_enabled": True}))
        request_state = request_stand_in()
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state)
            raise SerializationFailure("retry after admission")
        with self.db.cursor() as cr:
            self._admit(self._channel(cr), request_state).settle()
        with self.db.cursor() as cr:
            channel = self._channel(cr)
            rows = channel.env["integration.exchange"].search(
                [("channel_id", "=", f"device.channel,{channel.id}")], order="id"
            )
            self.assertEqual(rows.mapped("state"), ["failed", "success"])
        with self.assertRaises(Refused) as refused, self.db.cursor() as cr:
            self._admit(self._channel(cr))
        self.assertEqual(refused.exception.error_code, "duplicate_event")

    def test_another_requests_retry_of_a_failed_attempt_is_admitted(self):
        self._mutate(lambda c: c.write({"duplicate_detection_enabled": True}))
        with self.assertRaises(SerializationFailure), self.db.cursor() as cr:
            self._admit(self._channel(cr))
            raise SerializationFailure("rollback before replay")
        with self.db.cursor() as cr:
            self._admit(self._channel(cr)).settle()
        with self.assertRaises(Refused) as refused, self.db.cursor() as cr:
            self._admit(self._channel(cr))
        self.assertEqual(refused.exception.error_code, "duplicate_event")

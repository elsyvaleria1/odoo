from datetime import timedelta
from unittest.mock import patch

import psycopg

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.device.tests.common import DeviceHttpCase, DeviceTransactionCase


class EnrollmentFixture:
    def _enroll(self, **values):
        enrollment = self.env["device.enrollment"].create(
            {"name": "Machine enrollment", **values}
        )
        enrollment.action_provision_credential()
        enrollment.action_activate()
        return enrollment

    def _channel(self, enrollment, key="telemetry", **values):
        return self.env["device.channel"].create(
            {
                "name": "Machine channel",
                "enrollment_id": enrollment.id,
                "external_identifier": key,
                **values,
            }
        )


@tagged("post_install", "-at_install")
class TestChannelIdentity(EnrollmentFixture, DeviceTransactionCase):
    def test_integrity_probe_pages_and_reports_disabled_credentials(self):
        first = self._enroll()
        second = self._enroll()
        first.credential_id.active = False
        result = self.env["device.enrollment"]._probe_integrity(
            limit=1, after_id=first.id - 1
        )
        self.assertEqual(result["scanned"], 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(
            result["findings"], [{"id": first.id, "reasons": ["unusable_credential"]}]
        )
        following = self.env["device.enrollment"]._probe_integrity(
            limit=1, after_id=result["next_after_id"]
        )
        self.assertEqual(following["next_after_id"], second.id)
        self.assertFalse(following["findings"])
        user = new_test_user(self.env, login="probe-reader", groups="base.group_user")
        with self.assertRaises(AccessError):
            self.env["device.enrollment"].with_user(user)._probe_integrity()

    def test_software_enrollment_needs_no_hardware(self):
        enrollment = self._enroll()
        self.assertFalse(enrollment.device_id)
        first = self._channel(enrollment)
        second = self._channel(enrollment, "commands", purpose="commands")
        first.active = False
        self.assertTrue(second.active)
        self.assertEqual(first.credential_id, enrollment.credential_id)
        self.assertEqual(second.credential_id, enrollment.credential_id)

    def test_enrollments_cannot_share_their_authentication_credential(self):
        first = self._enroll()
        second = self._enroll()
        with self.assertRaises(psycopg.errors.UniqueViolation), self.env.cr.savepoint():
            second.credential_id = first.credential_id

    def test_channel_key_is_unique_within_enrollment_including_archive(self):
        enrollment = self._enroll()
        self._channel(enrollment, active=False)
        with self.assertRaises(psycopg.errors.UniqueViolation), self.env.cr.savepoint():
            self._channel(enrollment)
        other = self._enroll()
        self.assertTrue(self._channel(other))

    def test_revocation_cannot_be_undone_or_bypassed_by_modes(self):
        enrollment = self._enroll()
        channel = self._channel(enrollment)
        token = enrollment.credential_id.sudo().credential_value
        enrollment.action_revoke()
        for mode in ("enforce", "audit", "off"):
            allowed, _status, _reason, code = channel._decide_inbound_request(
                {"Authorization": f"Bearer {token}"},
                mode=mode,
            )
            self.assertFalse(allowed)
            self.assertEqual(code, "inactive_enrollment")
        with self.assertRaises(UserError):
            enrollment.action_activate()
        with self.assertRaises(UserError):
            enrollment.unlink()

    def test_archived_service_principal_cannot_admit_requests(self):
        enrollment = self._enroll()
        channel = self._channel(enrollment)
        token = enrollment.credential_id.sudo().credential_value
        enrollment.service_user_id.active = False
        allowed, _status, _reason, code = channel._decide_inbound_request(
            {"Authorization": f"Bearer {token}"}
        )
        self.assertFalse(allowed)
        self.assertEqual(code, "inactive_enrollment")

        enrollment.action_revoke()

    def test_identity_and_tenant_are_immutable(self):
        device = self._create_device_device(identifier="ENROLLED")
        enrollment = self._enroll(device_id=device.id)
        channel = self._channel(enrollment)
        company = self.env["res.company"].create({"name": "Other enrollment tenant"})
        for record, values in (
            (enrollment, {"company_id": company.id}),
            (enrollment, {"device_id": False}),
            (enrollment, {"state": "draft"}),
            (channel, {"external_identifier": "replacement"}),
            (channel, {"enrollment_id": self._enroll().id}),
            (channel, {"purpose": "commands"}),
            (channel, {"credential_id": False}),
            (device, {"company_id": company.id}),
        ):
            with self.subTest(values=values), self.assertRaises(UserError):
                record.write(values)

    def test_activation_requires_provisioned_company_credential(self):
        enrollment = self.env["device.enrollment"].create({"name": "Unprovisioned"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            enrollment.action_activate()
        other = self._enroll()
        other.credential_id.sudo().date_expiration = fields.Datetime.now() - timedelta(
            days=1
        )
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            enrollment.write(
                {"credential_id": other.credential_id.id, "state": "active"}
            )

    def test_fingerprint_follows_rotation_for_all_channels(self):
        enrollment = self._enroll()
        channels = self._channel(enrollment) | self._channel(enrollment, "other")
        old_token = enrollment.credential_id.sudo().credential_value
        self.assertTrue(all(channel.is_valid_token(old_token) for channel in channels))
        enrollment.action_provision_credential()
        new_token = enrollment.credential_id.sudo().credential_value
        self.assertNotEqual(old_token, new_token)
        self.assertFalse(any(channel.is_valid_token(old_token) for channel in channels))
        self.assertTrue(all(channel.is_valid_token(new_token) for channel in channels))

    def test_a_draft_channel_cannot_delete_its_exchange_evidence(self):
        enrollment = self.env["device.enrollment"].create({"name": "Draft history"})
        channel = self._channel(enrollment)
        exchange = self.env["integration.exchange"].create(
            {
                "direction": "inbound",
                "channel_id": f"device.channel,{channel.id}",
                "state": "refused",
                "refusal_reason": "inactive_enrollment",
            }
        )
        with self.assertRaises(UserError):
            channel.unlink()
        self.assertTrue(exchange.exists())
        self.assertTrue(channel.exists())

    def test_manager_provisions_without_general_vault_access(self):
        manager = new_test_user(
            self.env, login="channel_manager", groups="device.group_device_manager"
        )
        enrollment = (
            self.env["device.enrollment"]
            .with_user(manager)
            .create({"name": "Managed enrollment"})
        )
        enrollment.action_provision_credential()
        enrollment.action_activate()
        channel = (
            self.env["device.channel"]
            .with_user(manager)
            .create(
                {
                    "name": "Managed channel",
                    "enrollment_id": enrollment.id,
                    "external_identifier": "managed",
                }
            )
        )
        self.assertEqual(channel.company_id, enrollment.company_id)
        enrollment.read(["name", "key", "credential_id", "channel_ids"])
        channel.read(["name", "credential_id", "service_user_id"])
        with self.assertRaises(AccessError):
            enrollment.credential_id.credential_value
        enrollment.action_revoke()

    def test_tenant_guard_and_mismatched_bindings(self):
        company = self.env["res.company"].create({"name": "Private device tenant"})
        device = self._create_device_device(
            identifier="OTHER-TENANT", company_id=company.id
        )
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._enroll(device_id=device.id)
        other = self._enroll(company_id=company.id)
        channel = self._channel(other)
        user = new_test_user(
            self.env, login="channel_reader", groups="device.group_device_user"
        )
        self.assertFalse(
            self.env["device.channel"].with_user(user).search([("id", "=", channel.id)])
        )
        with self.assertRaises(AccessError):
            channel.with_user(user).read(["name"])


@tagged("post_install", "-at_install")
class TestChannelHttp(EnrollmentFixture, DeviceHttpCase):
    def _get(self, enrollment, key, token=None):
        return self.url_open(
            f"/device/v1/enrollments/{enrollment.key}/channels/{key}/status",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )

    def test_scoped_route_rotation_and_revocation(self):
        first = self._enroll()
        second = self._enroll()
        channel = self._channel(first)
        self._channel(second)
        token = first.credential_id.sudo().credential_value
        self.assertEqual(self._get(first, "telemetry").status_code, 401)
        self.assertEqual(self._get(first, "telemetry", token).status_code, 200)
        self.assertEqual(self._get(second, "telemetry", token).status_code, 401)
        first.action_provision_credential()
        self.assertEqual(self._get(first, "telemetry", token).status_code, 401)
        token = first.credential_id.sudo().credential_value
        self.assertEqual(self._get(first, "telemetry", token).status_code, 200)
        first.action_revoke()
        self.assertEqual(self._get(first, "telemetry", token).status_code, 403)
        with self.assertRaises(UserError):
            channel.unlink()

    def test_unprovisioned_enrollment_is_refused(self):
        enrollment = self.env["device.enrollment"].create({"name": "Not provisioned"})
        self._channel(enrollment)
        self.assertEqual(self._get(enrollment, "telemetry").status_code, 403)

    def test_http_retries_a_stale_admission_snapshot(self):
        enrollment = self._enroll()
        self._channel(enrollment)
        token = enrollment.credential_id.sudo().credential_value
        model = type(self.env["device.channel"])
        original = model._hold_inbound_authority
        attempts = []

        def conflict_once(channel):
            attempts.append(channel.id)
            if len(attempts) == 1:
                raise psycopg.errors.SerializationFailure("stale admission snapshot")
            return original(channel)

        with patch.object(model, "_hold_inbound_authority", conflict_once):
            response = self._get(enrollment, "telemetry", token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(attempts), 2)

    def test_disabled_channel_does_not_disable_its_sibling(self):
        enrollment = self._enroll()
        first = self._channel(enrollment)
        self._channel(enrollment, "commands", purpose="commands")
        token = enrollment.credential_id.sudo().credential_value
        first.active = False
        self.assertNotEqual(self._get(enrollment, "telemetry", token).status_code, 200)
        self.assertEqual(self._get(enrollment, "commands", token).status_code, 200)

    def test_http_retry_discards_previous_admission(self):
        enrollment = self._enroll()
        self._channel(enrollment)
        token = enrollment.credential_id.sudo().credential_value
        model = type(self.env["device.channel"])
        original_lock = model._hold_inbound_authority
        original_principal = model._inbound_service_user
        previous_admissions = []
        attempts = []

        def check_attempt(channel):
            previous_admissions.append(getattr(request, "admission", None))
            return original_lock(channel)

        def conflict_after_admission(channel):
            attempts.append(channel.id)
            if len(attempts) == 1:
                raise psycopg.errors.SerializationFailure("retry after admission")
            return original_principal(channel)

        with (
            patch.object(model, "_hold_inbound_authority", check_attempt),
            patch.object(model, "_inbound_service_user", conflict_after_admission),
        ):
            response = self._get(enrollment, "telemetry", token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(previous_admissions, [None, None])

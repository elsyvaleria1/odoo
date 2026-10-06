from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools import SQL

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestEnrollmentEvent(DeviceTransactionCase):
    def _events(self, record):
        return self.env["device.transport.event"].search(
            [("enrollment_ref", "=", record.id), ("subject_kind", "=", "enrollment")],
            order="id",
        )

    def test_lifecycle_records_actor_and_changes_without_secrets(self):
        manager = new_test_user(
            self.env, login="audit_manager", groups="device.group_device_manager"
        )
        enrollment = (
            self.env["device.enrollment"]
            .with_user(manager)
            .create({"name": "private label"})
        )
        enrollment.action_provision_credential()
        first = enrollment.credential_id.id
        enrollment.action_activate()
        enrollment.action_provision_credential()
        second = enrollment.credential_id.id
        enrollment.action_revoke()
        events = self._events(enrollment)
        self.assertEqual(
            events.mapped("event"),
            ["created", "changed", "changed", "changed", "changed"],
        )
        self.assertEqual(events.mapped("actor_id"), manager)
        self.assertEqual(events.mapped("actor_ref"), [manager.id] * 5)
        self.assertEqual(events[2].before["state"], "draft")
        self.assertEqual(events[2].after["state"], "active")
        self.assertEqual(events[3].before["credential_id"], first)
        self.assertEqual(events[3].after["credential_id"], second)
        self.assertEqual(events[4].after["state"], "revoked")
        self.assertNotIn(
            "private label",
            repr(
                events.read(["event", "actor_ref", "enrollment_ref", "before", "after"])
            ),
        )
        token = enrollment.credential_id.sudo().credential_value
        self.assertNotIn(
            token,
            repr(
                events.read(["event", "actor_ref", "enrollment_ref", "before", "after"])
            ),
        )

    def test_rpc_and_sudo_cannot_forge_rewrite_or_delete_events(self):
        enrollment = self.env["device.enrollment"].create({"name": "Immutable audit"})
        event = self._events(enrollment)
        with self.assertRaises(AccessError):
            event.create({"event": "deleted"})
        with self.assertRaises(AccessError):
            event.sudo().write({"event": "baseline"})
        with self.assertRaises(AccessError):
            event.sudo().with_context(_credential_log_cleanup_bypass=True).unlink()
        with self.assertRaises(ValueError):
            event._append(
                "changed", [(enrollment.id, None, {"token": "must never persist"})]
            )

    def test_draft_deletion_retains_company_and_numeric_identity(self):
        enrollment = self.env["device.enrollment"].create({"name": "Draft"})
        enrollment_ref = enrollment.id
        enrollment.unlink()
        events = self._events(enrollment)
        self.assertEqual(events.mapped("event"), ["created", "deleted"])
        self.assertFalse(events.enrollment_id)
        self.assertEqual(events.mapped("enrollment_ref"), [enrollment_ref] * 2)
        self.assertEqual(events.company_id, self.env.company)
        self.assertEqual(events[-1].before["state"], "draft")
        self.assertFalse(events[-1].after)

    def test_actor_deletion_preserves_numeric_attribution(self):
        manager = new_test_user(
            self.env,
            login="former_enrollment_manager",
            groups="device.group_device_manager",
        )
        enrollment = (
            self.env["device.enrollment"]
            .with_user(manager)
            .create({"name": "Former manager"})
        )
        event = self._events(enrollment)
        actor_ref = manager.id
        manager.unlink()
        self.assertFalse(event.actor_id)
        self.assertEqual(event.actor_ref, actor_ref)
        self.assertEqual(event.enrollment_ref, enrollment.id)

    def test_failed_transaction_rolls_back_state_and_journal(self):
        enrollment = self.env["device.enrollment"].create({"name": "Rollback"})
        enrollment.action_provision_credential()
        count = len(self._events(enrollment))
        with (
            self.assertRaisesRegex(RuntimeError, "later operation"),
            self.env.cr.savepoint(),
        ):
            enrollment.action_activate()
            self.assertEqual(len(self._events(enrollment)), count + 1)
            raise RuntimeError("later operation failed")
        self.assertEqual(enrollment.state, "draft")
        self.assertEqual(len(self._events(enrollment)), count)
        with (
            self.assertRaisesRegex(RuntimeError, "journal unavailable"),
            self.env.cr.savepoint(),
            patch.object(
                type(self.env["device.transport.event"]),
                "_append",
                side_effect=RuntimeError("journal unavailable"),
            ),
        ):
            enrollment.action_activate()
        self.assertEqual(enrollment.state, "draft")
        self.assertEqual(len(self._events(enrollment)), count)

    def test_noop_and_refused_changes_add_no_history(self):
        enrollment = self.env["device.enrollment"].create({"name": "Noop"})
        enrollment.with_context(tracking_disable=True).write({"state": "draft"})
        with self.assertRaises(UserError):
            enrollment.write({"key": "new-identity"})
        self.assertEqual(len(self._events(enrollment)), 1)
        enrollment.with_context(tracking_disable=True).action_revoke()
        self.assertEqual(len(self._events(enrollment)), 2)

    def test_probe_detects_missing_or_stale_journal(self):
        enrollment = self.env["device.enrollment"].create({"name": "Journal probe"})
        self.env.cr.execute(
            SQL(
                "UPDATE device_enrollment SET state = 'revoked' WHERE id = %s",
                enrollment.id,
            )
        )
        enrollment.invalidate_recordset(["state"])
        probe = enrollment._probe_integrity(limit=1, after_id=enrollment.id - 1)
        self.assertEqual(
            probe["findings"], [{"id": enrollment.id, "reasons": ["journal_drift"]}]
        )
        self.env.cr.execute(
            SQL(
                "DELETE FROM device_transport_event WHERE enrollment_ref = %s",
                enrollment.id,
            )
        )
        probe = enrollment._probe_integrity(limit=1, after_id=enrollment.id - 1)
        self.assertEqual(
            probe["findings"], [{"id": enrollment.id, "reasons": ["missing_journal"]}]
        )

    def test_batch_change_has_one_correlation(self):
        enrollments = self.env["device.enrollment"].create(
            [{"name": "First"}, {"name": "Second"}]
        )
        enrollments.action_revoke()
        events = self.env["device.transport.event"].search(
            [
                ("enrollment_ref", "in", enrollments.ids),
                ("event", "=", "changed"),
            ]
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(len(set(events.mapped("correlation_id"))), 1)


@tagged("post_install", "-at_install")
class TestChannelPolicyEvent(DeviceTransactionCase):
    def _channel(self):
        enrollment = self.env["device.enrollment"].create({"name": "Policy fixture"})
        return self.env["device.channel"].create(
            {
                "name": "Policy fixture",
                "enrollment_id": enrollment.id,
                "external_identifier": "policy",
            }
        )

    def _events(self, channel):
        return self.env["device.transport.event"].search(
            [("subject_kind", "=", "channel"), ("channel_ref", "=", channel.id)],
            order="id",
        )

    def test_policy_changes_are_scoped_and_not_observation_writes(self):
        channel = self._channel()
        channel.with_context(tracking_disable=True).write(
            {"rate_limit_requests": 20, "ip_whitelist": "192.0.2.0/24"}
        )
        channel.active = False
        events = self._events(channel)
        self.assertEqual(events.mapped("event"), ["created", "changed", "changed"])
        self.assertEqual(events[1].before["rate_limit_requests"], 100)
        self.assertEqual(events[1].after["rate_limit_requests"], 20)
        self.assertEqual(events[1].after["ip_whitelist"], "192.0.2.0/24")
        self.assertFalse(events[-1].after["active"])
        self.assertEqual(events.enrollment_id, channel.enrollment_id)
        channel.write({"active": False, "name": "Cosmetic rename"})
        channel.update_date_last_activity()
        self.assertEqual(self._events(channel), events)
        self.assertFalse(
            channel.enrollment_id._probe_integrity(
                limit=1, after_id=channel.enrollment_id.id - 1
            )["findings"]
        )

    def test_channel_and_owner_deletion_retain_original_references(self):
        channel = self._channel()
        enrollment = channel.enrollment_id
        channel_ref, enrollment_ref = channel.id, enrollment.id
        channel.unlink()
        enrollment.unlink()
        events = self._events(channel)
        self.assertEqual(events.mapped("event"), ["created", "deleted"])
        self.assertFalse(events.channel_id)
        self.assertFalse(events.enrollment_id)
        self.assertEqual(events.mapped("channel_ref"), [channel_ref] * 2)
        self.assertEqual(events.mapped("enrollment_ref"), [enrollment_ref] * 2)
        self.assertEqual(events.company_id, self.env.company)

    def test_policy_rollback_removes_its_event(self):
        channel = self._channel()
        with self.assertRaisesRegex(RuntimeError, "rollback"), self.env.cr.savepoint():
            channel.rate_limit_enabled = False
            self.assertEqual(len(self._events(channel)), 2)
            raise RuntimeError("rollback")
        self.assertTrue(channel.rate_limit_enabled)
        self.assertEqual(len(self._events(channel)), 1)

    def test_probe_covers_archived_channels_and_detects_drift(self):
        channel = self._channel()
        channel.active = False
        probe = channel._probe_integrity(limit=1, after_id=channel.id - 1)
        self.assertEqual(probe["scanned"], 1)
        self.assertFalse(probe["findings"])
        self.env.cr.execute(
            SQL(
                "UPDATE device_channel SET rate_limit_requests = 12 WHERE id = %s",
                channel.id,
            )
        )
        channel.invalidate_recordset(["rate_limit_requests"])
        self.assertEqual(
            channel._probe_integrity(limit=1, after_id=channel.id - 1)["findings"],
            [{"id": channel.id, "reasons": ["journal_drift"]}],
        )
        self.env.cr.execute(
            SQL(
                "DELETE FROM device_transport_event WHERE channel_ref = %s AND subject_kind = 'channel'",
                channel.id,
            )
        )
        self.assertEqual(
            channel._probe_integrity(limit=1, after_id=channel.id - 1)["findings"],
            [{"id": channel.id, "reasons": ["missing_journal"]}],
        )

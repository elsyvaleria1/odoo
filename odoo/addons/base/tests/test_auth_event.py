from datetime import timedelta
from unittest.mock import patch

from odoo import api, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user
from odoo.tools import SQL

from odoo.addons.base.models.auth_event import RETENTION_DAYS_DEFAULT


class TestAuthEvent(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = new_test_user(cls.env, login="auth_event_owner")
        cls.other = new_test_user(cls.env, login="auth_event_other")

    def _client(self):
        return self.env["auth.user.client"].create(
            {"user_id": self.owner.id, "recognition_key_hash": "event-fixture"}
        )

    def test_revoke_is_durable_and_scoped(self):
        client = self._client()
        session = self.env["auth.user.client.session"].create(
            {"client_id": client.id, "session_identifier": "private-store-reference"}
        )
        with patch(
            "odoo.addons.base.models.auth_user_client.root.session_store.remove_sessions_for_identifiers"
        ):
            client.with_user(self.owner)._revoke()
        events = self.env["auth.event"].search([("client_ref", "=", client.id)])
        self.assertEqual(
            set(events.mapped("event")), {"client_revoked", "session_revoked"}
        )
        self.assertEqual(events.mapped("actor_id"), self.owner)
        self.assertEqual(events.mapped("subject_user_id"), self.owner)
        self.assertEqual(
            events.filtered(lambda e: e.event == "session_revoked").session_ref,
            session.id,
        )
        self.assertEqual(
            events.filtered(lambda e: e.event == "client_revoked").generation, 1
        )
        self.assertEqual(
            self.env["auth.event"]
            .with_user(self.owner)
            .search([("id", "in", events.ids)]),
            events,
        )
        self.assertFalse(
            self.env["auth.event"]
            .with_user(self.other)
            .search([("id", "in", events.ids)])
        )
        client.unlink()
        self.assertEqual(events.exists(), events)
        self.assertNotIn("private-store-reference", repr(events.read()))
        self.assertTrue(all(events.mapped("correlation_id")))

    def test_an_empty_create_or_write_is_a_no_op_and_any_other_refuses(self):
        events = self.env["auth.event"]
        self.assertEqual(events.create([]), events.browse())
        self.assertIs(events.browse().write({}), True)
        event = events._append(
            [{"event": "other_sessions_ended", "subject_user_id": self.owner.id}]
        )
        with self.assertRaises(AccessError):
            event.write({})

    def test_expiry_removes_only_events_past_their_retention(self):
        old, recent = self.env["auth.event"]._append(
            [
                {"event": "other_sessions_ended", "subject_user_id": self.owner.id},
                {"event": "other_sessions_ended", "subject_user_id": self.other.id},
            ]
        )
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "UPDATE auth_event SET occurred_at = %s WHERE id = %s",
                fields.Datetime.now() - timedelta(days=RETENTION_DAYS_DEFAULT + 1),
                old.id,
            )
        )
        self.env.invalidate_all()
        expired, more = self.env["auth.event"]._gc_events()
        self.assertEqual(expired, 1)
        self.assertFalse(more)
        self.assertFalse(old.exists())
        self.assertEqual(recent.exists(), recent)

    def test_public_mutation_is_refused_even_for_superuser(self):
        events = self.env["auth.event"]._append(
            [{"event": "other_sessions_ended", "subject_user_id": self.owner.id}]
        )
        for model in (events.with_user(self.owner), events.sudo()):
            with self.assertRaises(AccessError):
                model.write({"event": "client_revoked"})
            with self.assertRaises(AccessError):
                model.unlink()
            with self.assertRaises(AccessError):
                model.create({"event": "client_revoked"})

    def test_rollback_removes_event_and_revocation(self):
        client = self._client()
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with self.env.cr.savepoint():
                client.with_user(self.owner)._revoke()
                self.assertTrue(
                    self.env["auth.event"].search([("client_ref", "=", client.id)])
                )
                raise RuntimeError("rollback")
        self.assertFalse(
            self.env["auth.event"].search([("client_ref", "=", client.id)])
        )
        self.assertTrue(client.active)
        self.assertEqual(client.session_generation, 0)

    def test_rolled_back_revocation_does_not_delete_stored_sessions(self):
        client = self._client()
        self.env["auth.user.client.session"].create(
            {
                "client_id": client.id,
                "session_identifier": "rollback-store-reference",
            }
        )
        hooks_before = len(self.env.cr.postcommit)
        with patch(
            "odoo.addons.base.models.auth_user_client.root.session_store.remove_sessions_for_identifiers"
        ) as cleanup:
            with (
                self.assertRaisesRegex(RuntimeError, "rollback"),
                self.env.cr.savepoint(),
            ):
                client.with_user(self.owner)._revoke()
                raise RuntimeError("rollback")
            cleanup.assert_not_called()
        self.assertEqual(len(self.env.cr.postcommit), hooks_before)
        self.assertTrue(client.active)
        self.assertTrue(client.session_ids.active)

    def test_ending_other_sessions_records_actor_and_generation(self):
        self.owner.with_user(self.owner)._end_other_sessions()
        event = self.env["auth.event"].search(
            [
                ("event", "=", "other_sessions_ended"),
                ("subject_user_id", "=", self.owner.id),
            ],
            limit=1,
        )
        self.assertEqual(event.actor_id, self.owner)
        self.assertEqual(event.generation, self.owner.session_epoch)

    def test_logout_without_authenticated_environment_keeps_subject(self):
        client = self._client()
        session = self.env["auth.user.client.session"].create(
            {"client_id": client.id, "session_identifier": "anonymous-logout"}
        )
        anonymous = api.Environment(self.env.cr, None, {})
        anonymous["auth.user.client.session"]._mark_logged_out(
            session.session_identifier
        )
        event = self.env["auth.event"].search([("session_ref", "=", session.id)])
        self.assertEqual(event.event, "session_logged_out")
        self.assertEqual(event.subject_user_id, self.owner)
        self.assertFalse(event.actor_id)
        self.assertFalse(event.actor_ref)
        self.assertFalse(session.active)

    def test_large_action_keeps_one_correlation_across_insert_batches(self):
        events = self.env["auth.event"]._append(
            [
                {
                    "event": "client_revoked",
                    "subject_user_id": self.owner.id,
                    "client_ref": ref,
                }
                for ref in range(1, 5501)
            ]
        )
        self.assertEqual(len(events), 5500)
        self.assertEqual(len(set(events.mapped("correlation_id"))), 1)
        self.assertEqual(set(events.mapped("client_ref")), set(range(1, 5501)))

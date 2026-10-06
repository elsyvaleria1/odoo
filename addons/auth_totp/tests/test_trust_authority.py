from unittest.mock import patch

from odoo.exceptions import AccessDenied
from odoo.http import root
from odoo.tests import TransactionCase


class TestTrustAuthority(TransactionCase):
    def test_trust_has_no_api_key_scope_or_issuance_policy(self):
        if not self._registry_patched:
            self.registry_enter_test_mode()
        user = self.env.ref("base.user_admin")
        trust, key = self.env["auth.totp.trust"].with_user(user)._issue("Trust probe")
        self.assertNotIn("key", trust._fields)
        self.assertNotIn("scope_id", trust._fields)
        self.assertFalse(hasattr(trust, "_generate"))
        self.assertTrue(trust._resolve_trust_id(key=key, uid=user.id))
        self.assertFalse(trust._resolve_trust_id(key=key, uid=self.env.uid))
        self.assertTrue(trust.expiration_date)

    def test_trust_revoked_after_verification_cannot_bind(self):
        user = self.env.ref("base.user_admin")
        trust, _key = (
            self.env["auth.totp.trust"].with_user(user)._issue("Revocation probe")
        )
        session = root.session_store.new()
        session.uid = user.id
        session["pre_totp_trust_id"] = trust.id
        self.env.cr.execute("DELETE FROM auth_totp_trust WHERE id = %s", [trust.id])
        clients = self.env["auth.user.client"].with_context(active_test=False)
        before = clients.search_count([])
        with self.assertRaises(AccessDenied), self.env.cr.savepoint():
            clients._bind_session(session)
        self.assertEqual(clients.search_count([]), before)
        self.assertNotIn("auth_client_id", session)

    def test_revoking_an_empty_trust_set_is_a_noop(self):
        user = self.env.ref("base.public_user")
        self.assertEqual(
            self.env["auth.totp.trust"].with_user(user)._remove(),
            {"type": "ir.actions.act_window_close"},
        )

    def test_trust_audit_survives_credential_deletion(self):
        user = self.env.ref("base.user_admin")
        trust, key = self.env["auth.totp.trust"].with_user(user)._issue("Audit probe")
        trust_id = trust.id
        trust._remove()
        events = self.env["auth.event"].search(
            [
                ("model_name", "=", "auth.totp.trust"),
                ("credential_ref", "=", trust_id),
            ]
        )
        self.assertEqual(
            set(events.mapped("event")), {"credential_issued", "credential_revoked"}
        )
        self.assertEqual(events.mapped("subject_user_id"), user)
        self.assertNotIn(key, repr(events.read()))
        self.assertFalse(trust.exists())

    def test_forgetting_a_client_revokes_every_trust_it_was_issued(self):
        user = self.env.ref("base.user_admin")
        client = (
            self.env["auth.user.client"]
            .create(
                {"user_id": user.id, "recognition_key_hash": "multiple-trust-probe"}
            )
            .with_user(user)
        )
        issued = self.env["auth.totp.trust"]
        with patch(
            "odoo.addons.auth_totp.models.auth_user_client._current_client_id",
            return_value=client.id,
        ):
            for name in ("First trust", "Second trust"):
                trust, _key = self.env["auth.totp.trust"].with_user(user)._issue(name)
                client._trust_current_client(trust.id)
                issued |= trust
        client._revoke()
        self.assertFalse(issued.exists())

    def test_trusted_login_links_the_grant_to_the_new_recognition_identity(self):
        user = self.env.ref("base.user_admin")
        trust, _key = (
            self.env["auth.totp.trust"].with_user(user)._issue("Reusable trust")
        )
        clients = self.env["auth.user.client"]
        identities = []
        for _ in range(2):
            session = root.session_store.new()
            session.uid = user.id
            session["pre_totp_trust_id"] = trust.id
            client, _inserted = clients._bind_session(session)
            identities.append(client)
            self.assertEqual(client.totp_trust_ids, trust)
        self.assertNotEqual(identities[0], identities[1])
        identities[1].with_user(user)._revoke()
        self.assertFalse(trust.exists())
        self.env.invalidate_all()
        self.assertFalse(identities[0].totp_trust_ids)

    def test_session_end_keeps_trust_and_retention_keeps_its_client(self):
        user = self.env.ref("base.user_admin")
        client = (
            self.env["auth.user.client"]
            .create(
                {
                    "user_id": user.id,
                    "recognition_key_hash": "retention-trust-probe",
                    "last_activity": "2000-01-01",
                }
            )
            .with_user(user)
        )
        trust, _key = (
            self.env["auth.totp.trust"].with_user(user)._issue("Retained trust")
        )
        client._link_totp_trust(trust.id, user.id)
        client._end_sessions()
        self.assertTrue(trust.exists())
        self.assertFalse(client.active)
        self.env.flush_all()
        self.env["auth.user.client"]._gc_revoked_clients()
        self.assertTrue(client.exists())
        trust._remove()
        self.env["auth.user.client"]._gc_revoked_clients()
        self.assertFalse(client.exists())

    def test_trust_cannot_be_linked_to_another_user(self):
        user = self.env.ref("base.user_admin")
        client = self.env["auth.user.client"].create(
            {"user_id": self.env.uid, "recognition_key_hash": "wrong-owner-trust-probe"}
        )
        trust, _key = self.env["auth.totp.trust"].with_user(user)._issue("Owner trust")
        with self.assertRaises(AccessDenied):
            client._link_totp_trust(trust.id, self.env.uid)
        self.assertFalse(client.totp_trust_ids)

    def test_forget_other_clients_includes_logged_out_clients_with_trust(self):
        user = self.env.ref("base.user_admin")
        client = (
            self.env["auth.user.client"]
            .create(
                {
                    "user_id": user.id,
                    "recognition_key_hash": "logged-out-trust-probe",
                }
            )
            .with_user(user)
        )
        trust, _key = (
            self.env["auth.totp.trust"].with_user(user)._issue("Logged out trust")
        )
        client._link_totp_trust(trust.id, user.id)
        client._end_sessions()
        self.assertFalse(client.active)
        user.with_user(user)._action_revoke_all_devices()
        self.assertFalse(
            trust.exists(), "Forgetting other clients must include retained trust"
        )

    def test_expired_retained_grant_does_not_display_as_trusted(self):
        user = self.env.ref("base.user_admin")
        client = self.env["auth.user.client"].create(
            {
                "user_id": user.id,
                "recognition_key_hash": "expired-badge-probe",
            }
        )
        trust, _key = self.env["auth.totp.trust"].with_user(user)._issue("Badge trust")
        client._link_totp_trust(trust.id, user.id)
        self.assertTrue(client.has_valid_totp_trust)
        trust.sudo().expiration_date = "2000-01-01"
        self.assertFalse(client.has_valid_totp_trust)
        self.assertEqual(
            client.totp_trust_ids, trust, "Expiry must not erase provenance"
        )

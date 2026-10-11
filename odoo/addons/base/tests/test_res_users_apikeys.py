from datetime import timedelta
from hashlib import sha256

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import AccessDenied, AccessError, ValidationError
from odoo.fields import Command
from odoo.tests.common import (
    TransactionCase,
    new_test_user,
    new_unbound_test_api_key,
    tagged,
)

from odoo.addons.base.tests.common import declare_api_scope


@tagged("post_install", "-at_install")
class TestResUsersApikeys(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="ak_user")
        cls.Apikeys = cls.env["res.users.apikeys"]

    def _generate(self, scope="rpc", hours=1):
        exp = fields.Datetime.now() + timedelta(hours=hours)
        return self.Apikeys.with_user(self.user)._generate(scope, "k", exp)

    def _cached_auth(self, key):
        self.env["res.users"]._check_uid_passwd_cached(
            self.user.id, key, sha256(key.encode()).hexdigest()
        )

    def test_check_credentials_valid(self):
        key = self._generate(scope="rpc")
        self.assertEqual(
            self.Apikeys._check_credentials(scope="rpc", key=key), self.user.id
        )

    def test_generate_refreshes_cached_user_keys(self):
        self.assertFalse(self.user.api_key_ids)
        self._generate()
        self.assertEqual(len(self.user.api_key_ids), 1)
        self._generate()
        self.assertEqual(len(self.user.api_key_ids), 2)

    def test_check_credentials_wrong_key(self):
        self._generate(scope="rpc")
        self.assertIsNone(self.Apikeys._check_credentials(scope="rpc", key="0" * 40))

    def test_check_credentials_empty_args_raise(self):
        with self.assertRaises(ValueError):
            self.Apikeys._check_credentials(scope="", key="x")
        with self.assertRaises(ValueError):
            self.Apikeys._check_credentials(scope="rpc", key="")

    def test_check_credentials_expired(self):
        key = self._generate(scope="rpc", hours=-1)
        self.assertIsNone(self.Apikeys._check_credentials(scope="rpc", key=key))

    def test_check_credentials_inactive_user(self):
        key = self._generate(scope="rpc")
        self.user.active = False
        self.env.flush_all()
        self.assertIsNone(self.Apikeys._check_credentials(scope="rpc", key=key))

    def test_expiration_date_system_bypass(self):
        self.Apikeys.sudo()._check_expiration_date(None)

    def test_expiration_date_required_for_non_system(self):
        with self.assertRaises(ValidationError):
            self.Apikeys.with_user(self.user)._check_expiration_date(None)

    def test_expiration_date_over_limit(self):
        too_far = fields.Datetime.now() + timedelta(days=3650)
        with self.assertRaises(ValidationError):
            self.Apikeys.with_user(self.user)._check_expiration_date(too_far)

    def test_gc_removes_expired_keys(self):
        valid = self._generate(scope="rpc", hours=1)
        expired = self._generate(scope="rpc", hours=-1)
        self.Apikeys._gc_user_apikeys()
        self.assertEqual(
            self.Apikeys._check_credentials(scope="rpc", key=valid), self.user.id
        )
        self.assertIsNone(self.Apikeys._check_credentials(scope="rpc", key=expired))

    def test_remove_other_users_key_raises(self):
        self._generate(scope="rpc")
        key_rec = self.Apikeys.sudo().search([("user_id", "=", self.user.id)], limit=1)
        other = new_test_user(self.env, login="ak_other")
        with self.assertRaises(AccessError):
            key_rec.with_user(other)._remove()

    def test_make_key_requires_internal_user(self):
        portal = new_test_user(self.env, login="ak_portal", groups="base.group_portal")
        with self.assertRaises(AccessError):
            self.env["wizard.res.users.apikeys.create"].with_user(
                portal
            ).check_access_generate_key()

    def test_generate_requires_internal_user(self):
        portal = new_test_user(
            self.env, login="ak_portal_gen", groups="base.group_portal"
        )
        exp = fields.Datetime.now() + timedelta(hours=1)
        with self.assertRaises(AccessError):
            self.Apikeys.with_user(portal)._generate("rpc", "k", exp)

    def test_check_credentials_scope_mismatch(self):
        declare_api_scope(self.env, "base.test_scope_x", "scope_x")
        declare_api_scope(self.env, "base.test_scope_y", "scope_y")
        key = self._generate(scope="scope_x")
        self.assertIsNone(self.Apikeys._check_credentials(scope="scope_y", key=key))

    def test_check_credentials_scope_match(self):
        declare_api_scope(self.env, "base.test_scope_x", "scope_x")
        key = self._generate(scope="scope_x")
        self.assertEqual(
            self.Apikeys._check_credentials(scope="scope_x", key=key), self.user.id
        )

    def test_check_credentials_null_scope_matches_rpc_alone(self):
        declare_api_scope(self.env, "base.test_scope_any", "anything")
        key = new_unbound_test_api_key(self.user)
        self.assertIsNone(self.Apikeys._check_credentials(scope="anything", key=key))
        self.assertEqual(
            self.Apikeys._check_credentials(scope="rpc", key=key), self.user.id
        )

    def test_generate_stores_hash_not_plaintext(self):
        key = self._generate(scope="rpc")
        self.assertEqual(len(key), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in key))
        self.env.cr.execute(
            "SELECT index, key FROM res_users_apikeys WHERE user_id = %s",
            (self.user.id,),
        )
        index, stored_key = self.env.cr.fetchone()
        self.assertEqual(index, key[:8])
        self.assertNotEqual(stored_key, key)
        self.assertTrue(stored_key.startswith("$pbkdf2-sha512$"))

    def test_remove_invalidates_cached_credentials(self):
        key = self._generate()
        self._cached_auth(key)
        self.Apikeys.sudo().search([("user_id", "=", self.user.id)])._remove()
        with self.assertRaises(AccessDenied):
            self._cached_auth(key)

    def test_api_key_ids_not_writable_through_self_service(self):
        exp = fields.Datetime.now() + timedelta(hours=1)
        victim = new_test_user(self.env, login="ak_victim")
        self.Apikeys.with_user(victim)._generate("rpc", "victim key", exp)
        victim_key = self.Apikeys.sudo().search([("user_id", "=", victim.id)])

        attacker = self.user.with_user(self.user)
        for command in (Command.delete(victim_key.id), Command.link(victim_key.id)):
            with self.assertRaises(AccessError):
                attacker.write({"api_key_ids": [command]})

        self.assertTrue(victim_key.exists(), "the victim's key was destroyed")
        self.assertEqual(victim_key.user_id, victim, "the victim's key was stolen")

    def test_gc_invalidates_cached_credentials(self):
        key = self._generate()
        self._cached_auth(key)
        self.env.cr.execute(
            """
            UPDATE res_users_apikeys
            SET expiration_date = (now() at time zone 'utc') - interval '1 day'
            WHERE user_id = %s
            """,
            (self.user.id,),
        )
        self.Apikeys._gc_user_apikeys()
        with self.assertRaises(AccessDenied):
            self._cached_auth(key)

    def test_the_wizard_names_the_door_of_every_key(self):
        wizard = (
            self.env["wizard.res.users.apikeys.create"]
            .with_user(self.user)
            .create({"name": "w", "duration": "1"})
        )
        self.assertEqual(wizard.scope_id, self.env.ref("base.apikeys_scope_rpc"))
        self.assertTrue(wizard._fields["scope_id"].required)

    def test_description_batch_create(self):
        Description = self.env["wizard.res.users.apikeys.create"].with_user(self.user)
        wizards = Description.create(
            [{"name": "a", "duration": "1"}, {"name": "b", "duration": "1"}]
        )
        self.assertEqual(len(wizards), 2)
        too_far = fields.Datetime.now() + timedelta(days=3650)
        with self.assertRaises(ValidationError):
            Description.create(
                [
                    {"name": "a", "duration": "1"},
                    {"name": "b", "duration": "-1", "expiration_date": too_far},
                ]
            )

    def test_check_credentials_persistent_key_never_expires(self):
        admin = self.env.ref("base.user_admin")
        key = self.Apikeys.with_user(admin)._generate("rpc", "persistent", None)
        self.assertEqual(
            self.Apikeys._check_credentials(scope="rpc", key=key),
            admin.id,
        )

    def test_issuing_and_removing_a_key_are_authentication_events(self):
        expiration = fields.Datetime.now() + timedelta(hours=1)
        self.Apikeys.with_user(self.user)._generate("rpc", "audited", expiration)
        record = self.Apikeys.search([("user_id", "=", self.user.id)], limit=1)
        events = self.env["auth.event"].sudo()
        domain = [
            ("model_name", "=", "res.users.apikeys"),
            ("credential_ref", "=", record.id),
            ("subject_user_id", "=", self.user.id),
        ]
        self.assertEqual(events.search(domain).mapped("event"), ["credential_issued"])
        record.with_user(self.user)._remove()
        self.assertEqual(
            sorted(events.search(domain).mapped("event")),
            ["credential_issued", "credential_revoked"],
        )

    def test_the_universal_door_reports_the_key_expiration(self):
        expiration = fields.Datetime.now() + timedelta(hours=1)
        key = self.Apikeys.with_user(self.user)._generate("rpc", "k", expiration)
        self.assertEqual(
            self.Apikeys._match_key("rpc", key), (self.user.id, expiration)
        )
        self.assertIsNone(self.Apikeys._match_key("rpc", "0" * 40))

    def test_a_cached_key_stops_authenticating_when_it_expires(self):
        key = self._generate(hours=1)
        Users = self.env["res.users"]
        Users._check_uid_passwd(self.user.id, key)
        with freeze_time(fields.Datetime.now() + timedelta(hours=2)):
            with self.assertRaises(AccessDenied):
                Users._check_uid_passwd(self.user.id, key)

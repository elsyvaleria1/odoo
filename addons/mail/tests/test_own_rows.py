import contextlib
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

BROWSER_KEYS = {
    "p256dh": "BGbhnoP_91U7oR59BaaSx0JnDv2oEooYnJRV2AbY5TBeKGCRCf0HcIJ9bOKchUCDH4cHYWo9SYDz3U-8vSxPL_A",
    "auth": "DJFdtAgZwrT6yYkUMgUqow",
}


@tagged("-at_install", "post_install")
class TestOwnRows(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal = new_test_user(
            cls.env, login="ownrow_p", groups="base.group_portal"
        )
        cls.other = new_test_user(cls.env, login="ownrow_o", groups="base.group_user")
        cls.portal_env = cls.env(user=cls.portal)

    def test_a_portal_user_formats_their_own_settings(self):
        settings = self.portal_env["res.users.settings"]._get_or_create_for_user(
            self.portal_env.user
        )
        self.assertFalse(settings.env.su)
        self.assertEqual(
            settings._res_users_settings_format()["volumes"], [("ADD", [])]
        )

    def test_a_field_kept_from_the_user_is_left_out_of_their_settings(self):
        settings = self.portal_env["res.users.settings"]._get_or_create_for_user(
            self.portal_env.user
        )
        kept = next(
            name
            for name in settings._res_users_settings_format()
            if name not in ("id", "volumes") and name in settings._fields
        )
        hide = settings._has_field_access.__func__

        def has_field_access(record, field, operation):
            return field.name != kept and hide(record, field, operation)

        with patch.object(
            self.registry["res.users.settings"], "_has_field_access", has_field_access
        ):
            self.assertNotIn(kept, settings._res_users_settings_format())

    def test_a_portal_user_keeps_their_own_presence(self):
        presences = self.portal_env["mail.presence"]
        presences._update_presence(self.portal_env.user)
        presence = self.env["mail.presence"].search([("user_id", "=", self.portal.id)])
        self.assertEqual(presence.status, "online")
        presences._update_presence(self.portal_env.user, inactivity_period=3600 * 1000)
        self.assertEqual(presence.status, "away")

    def test_a_portal_user_reaches_no_one_elses_presence(self):
        presences = self.env["mail.presence"]
        presences._update_presence(self.other)
        with contextlib.suppress(AccessError):
            self.portal_env["mail.presence"]._update_presence(
                self.other, inactivity_period=3600 * 1000
            )
        self.assertEqual(
            presences.search([("user_id", "=", self.other.id)]).status, "online"
        )
        self.assertFalse(
            self.portal_env["mail.presence"].search([("user_id", "=", self.other.id)])
        )
        absent = new_test_user(self.env, login="ownrow_a", groups="base.group_user")
        with self.assertRaises(AccessError):
            self.portal_env["mail.presence"]._update_presence(absent)

    def _register(self, env, endpoint):
        with patch.object(
            self.registry["mail.push.device"],
            "_is_vapid_public_key_current",
            return_value=True,
        ):
            env["mail.push.device"].register_devices(
                endpoint=endpoint, keys=BROWSER_KEYS, vapid_public_key="current"
            )

    def test_a_portal_user_registers_and_drops_their_own_device(self):
        self._register(self.portal_env, "https://push.example.com/portal")
        devices = self.portal_env["mail.push.device"].search([])
        self.assertEqual(devices.partner_id, self.portal.partner_id)
        self.portal_env["mail.push.device"].unregister_devices(
            endpoint="https://push.example.com/portal"
        )
        self.assertFalse(
            self.env["mail.push.device"].search(
                [("partner_id", "=", self.portal.partner_id.id)]
            )
        )

    def test_a_portal_user_reaches_no_one_elses_device(self):
        self._register(self.env(user=self.other), "https://push.example.com/other")
        self.assertFalse(self.portal_env["mail.push.device"].search([]))
        self.portal_env["mail.push.device"].unregister_devices(
            endpoint="https://push.example.com/other"
        )
        self.assertTrue(
            self.env["mail.push.device"].search(
                [("endpoint", "=", "https://push.example.com/other")]
            )
        )

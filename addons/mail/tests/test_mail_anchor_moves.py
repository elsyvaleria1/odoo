from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestOwnRowsStayOwned(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = new_test_user(cls.env, "anchor_owner", groups="base.group_portal")
        cls.victim = new_test_user(cls.env, "anchor_victim", groups="base.group_user")

    def test_a_push_device_cannot_be_moved_to_another_partner(self):
        device = (
            self.env["mail.push.device"]
            .sudo()
            .create(
                {
                    "partner_id": self.owner.partner_id.id,
                    "endpoint": "https://push.example.com/anchor-owner",
                    "keys": '{"p256dh": "x", "auth": "y"}',
                }
            )
            .with_user(self.owner)
        )
        with self.assertRaises(AccessError):
            device.write({"partner_id": self.victim.partner_id.id})
        device.write({"partner_id": self.owner.partner_id.id})

    def test_a_presence_cannot_be_moved_to_another_user(self):
        presence = (
            self.env["mail.presence"]
            .sudo()
            .create({"user_id": self.owner.id, "status": "online"})
            .with_user(self.owner)
        )
        with self.assertRaises(AccessError):
            presence.write({"user_id": self.victim.id})

    def test_a_volume_cannot_be_moved_to_another_users_settings(self):
        Settings = self.env["res.users.settings"].sudo()
        mine = Settings._get_or_create_for_user(self.owner)
        theirs = Settings._get_or_create_for_user(self.victim)
        volume = (
            self.env["res.users.settings.volumes"]
            .sudo()
            .create(
                {"user_setting_id": mine.id, "partner_id": self.victim.partner_id.id}
            )
            .with_user(self.owner)
        )
        with self.assertRaises(AccessError):
            volume.write({"user_setting_id": theirs.id})

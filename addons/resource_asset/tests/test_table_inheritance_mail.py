from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAssetSubtypeThread(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Device = cls.env["resource.asset.device"]
        cls.kind = cls.env.ref("resource_asset.kind_device")
        cls.user = cls.env["res.users"].create(
            {
                "name": "Asset Clerk",
                "login": "asset_clerk_thread",
                "group_ids": [
                    Command.link(cls.env.ref("base.group_user").id),
                    Command.link(cls.env.ref("resource_asset.group_asset_user").id),
                ],
            }
        )

    def _device(self):
        return self.Device.create({"name": "Scanner", "kind_id": self.kind.id})

    def test_the_creator_follows_the_row_under_its_resource(self):
        device = self.Device.with_user(self.user).create(
            {"name": "Scanner", "kind_id": self.kind.id}
        )
        followers = self.env["mail.followers"].search([("res_id", "=", device.id)])
        self.assertEqual(followers.mapped("res_model"), ["resource.resource"])
        self.assertEqual(device.message_partner_ids, self.user.partner_id)

    def test_the_subtype_fetches_the_messages_posted_on_its_row(self):
        device = self._device()
        message = device.message_post(body="Serviced", message_type="comment")
        self.assertEqual(message.model, "resource.resource")
        fetched = self.env["mail.message"]._message_fetch(None, thread=device)
        self.assertIn(message, fetched["messages"])
        searched = self.env["mail.message"]._message_fetch(
            None, thread=device, search_term="Serviced"
        )
        self.assertEqual(searched["messages"], message)

    def test_deleting_the_subtype_row_deletes_its_activities(self):
        device = self._device()
        activity = device.activity_schedule("mail.mail_activity_data_todo")
        self.assertEqual(activity.res_model, "resource.resource")
        device.unlink()
        self.assertFalse(activity.exists())

    def test_the_activity_view_of_the_subtype_holds_its_activities(self):
        device = self._device()
        activity = device.activity_schedule("mail.mail_activity_data_todo")
        data = self.env["mail.activity"].get_activity_data(
            "resource.asset.device", [("id", "=", device.id)]
        )
        self.assertEqual(data["activity_res_ids"], [device.id])
        self.assertIn(
            activity.activity_type_id.id, [t["id"] for t in data["activity_types"]]
        )

    def test_a_subscription_is_seen_from_every_model_of_the_row(self):
        device = self._device()
        root = self.env["resource.asset"].browse(device.id)
        partner = self.env["res.partner"].create({"name": "Watcher"})
        self.assertNotIn(partner, device.message_partner_ids)
        self.assertNotIn(partner, root.message_partner_ids)
        root.message_subscribe(partner_ids=partner.ids)
        self.assertIn(partner, device.message_partner_ids)
        self.assertIn(partner, root.message_partner_ids)
        device.message_unsubscribe(partner_ids=partner.ids)
        self.assertNotIn(partner, root.message_partner_ids)
        self.assertNotIn(partner, device.message_partner_ids)

    def test_a_message_and_its_attachment_are_seen_from_every_model_of_the_row(self):
        device = self._device()
        root = self.env["resource.asset"].browse(device.id)
        messages_before = device.message_ids
        self.assertEqual(device.message_attachment_count, 0)
        message = root.message_post(body="Serviced", message_type="comment")
        self.assertEqual(device.message_ids, messages_before | message)
        self.env["ir.attachment"].create(
            {
                "name": "manual.txt",
                "raw": b"manual",
                "res_model": "resource.resource",
                "res_id": root.id,
            }
        )
        self.assertEqual(device.message_attachment_count, 1)

from markupsafe import Markup

from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestHomeTileInbox(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login="tile_inbox",
            groups="base.group_user",
            notification_type="inbox",
        )
        cls.partner = cls.env["res.partner"].create({"name": "Azure Interior"})

    def _notify(self, body):
        return self.partner.message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            partner_ids=self.user.partner_id.ids,
        )

    def _inbox(self):
        return (
            self.env["home.tile"]
            .with_user(self.user)
            .get_tiles([{"id": "inbox_1", "type": "inbox"}])["inbox_1"]["data"]
        )

    def test_the_inbox_counts_and_lists_the_latest_messages_to_read(self):
        self._notify(Markup("<p>First</p>"))
        latest = self._notify(Markup("<p>Second <b>one</b></p>"))
        data = self._inbox()
        self.assertEqual(data["count"], 2)
        self.assertEqual([m["id"] for m in data["messages"]][0], latest.id)
        self.assertEqual(data["messages"][0]["preview"], "Second one")
        self.assertEqual(data["messages"][0]["record_name"], "Azure Interior")
        self.assertEqual(
            (data["messages"][0]["model"], data["messages"][0]["res_id"]),
            ("res.partner", self.partner.id),
        )

    def test_a_message_on_a_record_out_of_reach_opens_the_inbox_instead(self):
        elsewhere = self.env["res.company"].create({"name": "Elsewhere"})
        hidden = self.env["res.partner"].create(
            {"name": "Hidden", "company_id": elsewhere.id}
        )
        self.assertFalse(hidden.with_user(self.user).has_access("read"))
        hidden.message_post(
            body=Markup("<p>About a hidden contact</p>"),
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            partner_ids=self.user.partner_id.ids,
        )
        [message] = self._inbox()["messages"]
        self.assertEqual((message["model"], message["res_id"]), (False, False))

    def test_a_read_message_leaves_the_inbox(self):
        message = self._notify(Markup("<p>Read me</p>"))
        message.with_user(self.user).set_message_done()
        data = self._inbox()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["messages"], [])

    def test_the_inbox_tile_keeps_its_statement_count(self):
        self._notify(Markup("<p>On a contact</p>"))
        elsewhere = self.env["res.company"].create({"name": "Elsewhere"})
        for partner in (
            self.user.partner_id,
            self.env["res.partner"].create(
                {"name": "Hidden", "company_id": elsewhere.id}
            ),
        ):
            partner.message_post(
                body=Markup("<p>Another</p>"),
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                partner_ids=self.user.partner_id.ids,
            )
        request = [{"id": "inbox_1", "type": "inbox"}]
        self.env["home.tile"].with_user(self.user).get_tiles(request)
        self.env.invalidate_all()
        with self.assertQueryCount(11):
            self.env["home.tile"].with_user(self.user).get_tiles(request)

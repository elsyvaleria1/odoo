from contextlib import suppress

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSavepointDiscardsCommitHooks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env["discuss.channel"]._create_channel(
            name="Savepoint hooks", group_id=None
        )
        cls.env.cr.flush()

    def _hooks_state(self):
        cr = self.env.cr
        return (
            len(cr.precommit),
            len(cr.postcommit),
            len(cr.precommit.data.get("bus.bus.values", ())),
            list(cr.postcommit.data.get("bus.bus.channels", ())),
        )

    def _bus_rows(self, body):
        self.env.cr.flush()
        return self.env["bus.bus"].sudo().search([("message", "like", body)])

    def test_rolled_back_post_notifies_nobody(self):
        before = self._hooks_state()
        with suppress(ValueError), self.env.cr.savepoint():
            self.channel.message_post(body="GHOST", message_type="comment")
            raise ValueError
        self.assertFalse(
            self.env["mail.message"].search([("body", "like", "GHOST")]),
            "the savepoint rolled the message back",
        )
        after = self._hooks_state()
        self.assertFalse(self._bus_rows("GHOST"), "a notification for no message")
        self.assertEqual(after, before)

    def test_post_before_the_savepoint_still_notifies(self):
        self.channel.message_post(body="KEPT", message_type="comment")
        kept = self._hooks_state()
        with suppress(ValueError), self.env.cr.savepoint(flush=False):
            self.channel.message_post(body="GHOST", message_type="comment")
            raise ValueError
        after = self._hooks_state()
        self.assertFalse(self._bus_rows("GHOST"), "a notification for no message")
        self.assertTrue(self._bus_rows("KEPT"))
        self.assertEqual(after, kept)

    def test_released_savepoint_keeps_its_notification(self):
        with self.env.cr.savepoint():
            self.channel.message_post(body="RELEASED", message_type="comment")
        self.assertTrue(self._bus_rows("RELEASED"))

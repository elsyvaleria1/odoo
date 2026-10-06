from odoo.db import db_connect
from odoo.exceptions import ConcurrencyError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestConcurrentAiChatOpening(TransactionCase):
    def setUp(self):
        super().setUp()
        self.admin = self.env.ref("base.user_admin")
        with db_connect(self.env.cr.dbname).cursor() as cr:
            agent = self.env(cr=cr)["ai.agent"].create({"name": "ai chat race"})
            cr.commit()
            self.agent_id = agent.id
            self.agent_partner_id = agent.partner_id.id
        self.addCleanup(self._drop_committed_rows)

    def _drop_committed_rows(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            chat_ids = self._get_committed_chat_ids(cr)
            cr.execute(
                "DELETE FROM mail_message WHERE model = 'discuss.channel'"
                " AND res_id = ANY(%s)",
                [chat_ids],
            )
            cr.execute("DELETE FROM discuss_channel WHERE id = ANY(%s)", [chat_ids])
            cr.execute("DELETE FROM ai_agent WHERE id = %s", [self.agent_id])
            cr.execute("DELETE FROM res_partner WHERE id = %s", [self.agent_partner_id])
            cr.commit()

    def _get_committed_chat_ids(self, cr):
        cr.execute(
            "SELECT id FROM discuss_channel"
            " WHERE channel_type = 'ai_chat' AND ai_agent_id = %s ORDER BY id",
            [self.agent_id],
        )
        return [row[0] for row in cr.fetchall()]

    def _open_chat(self, cr):
        env = self.env(cr=cr, user=self.admin)
        return env["ai.agent"].browse(self.agent_id)._get_or_create_ai_chat().id

    def test_two_openings_of_the_agent_chat_create_one_channel(self):
        with (
            self.leave_registry_test_mode(),
            db_connect(self.env.cr.dbname).cursor() as cr_a,
            db_connect(self.env.cr.dbname).cursor() as cr_b,
        ):
            cr_b.execute("SELECT 1")
            opened_by_a = self._open_chat(cr_a)
            cr_a.commit()
            retries = 0
            while True:
                try:
                    opened_by_b = self._open_chat(cr_b)
                    cr_b.commit()
                    break
                except ConcurrencyError:
                    retries += 1
                    cr_b.rollback()
                    if retries > 1:
                        raise
            committed = self._get_committed_chat_ids(cr_b)
        self.assertEqual(
            committed,
            [opened_by_a],
            "the opening whose snapshot predates the first commit made a second chat",
        )
        self.assertEqual(opened_by_b, opened_by_a)
        self.assertEqual(retries, 1)

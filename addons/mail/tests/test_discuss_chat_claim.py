from odoo.db import db_connect
from odoo.exceptions import ConcurrencyError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestConcurrentChatOpening(TransactionCase):
    def setUp(self):
        super().setUp()
        self.admin = self.env.ref("base.user_admin")
        with db_connect(self.env.cr.dbname).cursor() as cr:
            peer = self.env(cr=cr)["res.partner"].create({"name": "chat claim peer"})
            cr.commit()
            self.peer_id = peer.id
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
            cr.execute("DELETE FROM res_partner WHERE id = %s", [self.peer_id])
            cr.commit()

    def _get_committed_chat_ids(self, cr):
        cr.execute(
            "SELECT c.id FROM discuss_channel c"
            " JOIN discuss_channel_member m ON m.channel_id = c.id"
            " WHERE c.channel_type = 'chat'"
            " GROUP BY c.id"
            " HAVING array_agg(m.partner_id ORDER BY m.partner_id) = %s::int[]"
            " ORDER BY c.id",
            [sorted([self.admin.partner_id.id, self.peer_id])],
        )
        return [row[0] for row in cr.fetchall()]

    def _open_chat(self, cr):
        return (
            self.env(cr=cr, user=self.admin)["discuss.channel"]
            ._get_or_create_chat([self.peer_id])
            .id
        )

    def test_two_openings_of_the_same_chat_create_one_channel(self):
        with (
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
        self.assertEqual(retries, 1, "the stale opening retried once")

    def test_a_stale_chat_member_set_does_not_refuse_the_chat(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            first = self._open_chat(cr)
            cr.execute(
                "DELETE FROM discuss_channel_member"
                " WHERE channel_id = %s AND partner_id = %s",
                [first, self.peer_id],
            )
            cr.commit()
            self.env(cr=cr).invalidate_all()
            second = self._open_chat(cr)
            cr.commit()
            cr.execute(
                "SELECT id, chat_member_set FROM discuss_channel WHERE id = ANY(%s) ORDER BY id",
                [[first, second]],
            )
            keys = cr.fetchall()
            cr.execute("DELETE FROM discuss_channel WHERE id = %s", [first])
            cr.commit()
        self.assertNotEqual(second, first)
        self.assertEqual(
            keys,
            [
                (first, None),
                (
                    second,
                    ",".join(
                        map(str, sorted([self.admin.partner_id.id, self.peer_id]))
                    ),
                ),
            ],
        )

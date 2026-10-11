from datetime import timedelta

from odoo import fields
from odoo.db import db_connect
from odoo.service.transaction import retrying
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install", "access_link")
class TestInvitationLinkRaces(TransactionCase):
    def setUp(self):
        super().setUp()
        now = fields.Datetime.now().replace(microsecond=0)
        self.far = now + timedelta(days=700)
        self.near = now + timedelta(days=5)
        self.addCleanup(self.drop_committed)

    def cursor(self):
        return db_connect(self.env.cr.dbname).cursor()

    def drop_committed(self):
        with self.cursor() as cr:
            cr.execute(
                "SELECT id FROM calendar_event WHERE name = 'race meeting'",
            )
            event_ids = [row[0] for row in cr.fetchall()]
            cr.execute(
                "DELETE FROM access_link WHERE res_model = 'calendar.attendee' "
                "AND res_id IN (SELECT id FROM calendar_attendee "
                "WHERE event_id = ANY(%s))",
                [event_ids],
            )
            cr.execute("DELETE FROM calendar_event WHERE id = ANY(%s)", [event_ids])
            cr.execute("DELETE FROM res_partner WHERE name LIKE 'race guest%%'")
            cr.commit()

    def committed_meeting(self):
        with self.cursor() as cr:
            env = self.env(cr=cr, su=True)
            guest = env["res.partner"].create({"name": "race guest"})
            event = env["calendar.event"].create(
                {
                    "name": "race meeting",
                    "start": self.far,
                    "stop": self.far + timedelta(hours=1),
                }
            )
            cr.commit()
            return event.id, guest.id

    def run_as_a_request(self, cr, work):
        env = self.env(cr=cr, su=True)
        attempts = []

        def attempt():
            attempts.append(len(attempts) + 1)
            return work(env, attempts[-1])

        with mute_logger("odoo.db.cursor", "odoo.service.model"):
            retrying(attempt, env)
        return len(attempts)

    def invite(self, env, event_id, guest_id):
        env["calendar.attendee"].create({"event_id": event_id, "partner_id": guest_id})

    def move(self, env, event_id):
        env["calendar.event"].browse(event_id).write(
            {"start": self.near, "stop": self.near + timedelta(hours=1)}
        )

    def link_dates(self, event_id, guest_id):
        with self.cursor() as cr:
            cr.execute(
                "SELECT link.date_to FROM access_link link "
                "JOIN calendar_attendee attendee ON attendee.id = link.res_id "
                "WHERE link.res_model = 'calendar.attendee' "
                "AND attendee.event_id = %s AND attendee.partner_id = %s",
                [event_id, guest_id],
            )
            return [row[0] for row in cr.fetchall()]

    def test_an_attendee_invited_across_a_move_gets_the_moved_date(self):
        event_id, guest_id = self.committed_meeting()
        with self.cursor() as cr_invite, self.cursor() as cr_move:

            def invite(env, attempt):
                env["calendar.event"].browse(event_id).name
                if attempt == 1:
                    self.move(self.env(cr=cr_move, su=True), event_id)
                    cr_move.commit()
                self.invite(env, event_id, guest_id)

            attempts = self.run_as_a_request(cr_invite, invite)
        expiry = self.near + timedelta(hours=1, days=30)
        self.assertEqual(self.link_dates(event_id, guest_id), [expiry])
        self.assertEqual(attempts, 2, "the invitation must fail to serialize")

    def test_a_meeting_moved_across_an_invitation_moves_the_new_link(self):
        event_id, guest_id = self.committed_meeting()
        with self.cursor() as cr_move, self.cursor() as cr_invite:

            def move(env, attempt):
                env["calendar.event"].browse(event_id).name
                if attempt == 1:
                    self.invite(self.env(cr=cr_invite, su=True), event_id, guest_id)
                    cr_invite.commit()
                self.move(env, event_id)

            attempts = self.run_as_a_request(cr_move, move)
        expiry = self.near + timedelta(hours=1, days=30)
        self.assertEqual(self.link_dates(event_id, guest_id), [expiry])
        self.assertEqual(attempts, 2, "the move must fail to serialize")

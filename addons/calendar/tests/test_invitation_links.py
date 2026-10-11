from datetime import timedelta

from odoo import fields
from odoo.tests.common import HttpCase, new_test_user, tagged

from odoo.addons.base.models.access_link import hash_token


@tagged("post_install", "-at_install", "access_link")
class TestInvitationLinks(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.guest = new_test_user(cls.env, "invitation_guest", tz="UTC").partner_id
        start = fields.Datetime.now().replace(microsecond=0) + timedelta(days=10)
        cls.event, cls.other_event = cls.env["calendar.event"].create(
            [
                {
                    "name": name,
                    "start": start,
                    "stop": start + timedelta(hours=1),
                    "partner_ids": [(4, cls.guest.id)],
                }
                for name in ("Planning", "Review")
            ]
        )

    def _attendee(self, event=None):
        return (event or self.event).attendee_ids.filtered(
            lambda attendee: attendee.partner_id == self.guest
        )

    def _links(self, record):
        return (
            self.env["access.link"]
            .sudo()
            .search([("res_model", "=", record._name), ("res_id", "=", record.id)])
        )

    def test_an_attendee_is_invited_through_a_link_in_their_name(self):
        attendee = self._attendee()
        link = self._links(attendee)
        self.assertEqual(
            (len(link), link.partner_id, link.role, link.cause),
            (1, self.guest, "comment", "notification"),
        )
        self.assertEqual(link.date_to, self.event.stop + timedelta(days=30))
        self.assertEqual(link.token_hash, hash_token(attendee.sudo().access_token))
        self.env.cr.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'calendar_attendee' AND column_name = 'access_token'"
        )
        self.assertEqual(self.env.cr.fetchone()[0], 0, "no token is kept in clear")

    def test_moving_the_meeting_moves_its_links(self):
        attendee = self._attendee()
        later = self.event.stop + timedelta(days=60)
        self.event.write({"start": later - timedelta(hours=1), "stop": later})
        self.assertEqual(self._links(attendee).date_to, later + timedelta(days=30))

    def test_shortening_the_meeting_moves_its_links(self):
        attendee = self._attendee()
        self.event.write({"duration": 2000.0})
        self.assertEqual(
            self._links(attendee).date_to, self.event.stop + timedelta(days=30)
        )
        self.event.write({"duration": 1.0})
        self.assertEqual(
            self._links(attendee).date_to, self.event.stop + timedelta(days=30)
        )

    def test_a_meeting_far_ahead_keeps_its_link_until_a_month_after_it(self):
        far = fields.Datetime.now().replace(microsecond=0) + timedelta(days=730)
        event = self.env["calendar.event"].create(
            {
                "name": "Anniversary",
                "start": far,
                "stop": far + timedelta(hours=1),
                "partner_ids": [(4, self.guest.id)],
            }
        )
        month_after = far + timedelta(hours=1, days=30)
        self.assertEqual(self._links(self._attendee(event)).date_to, month_after)
        self.event.write({"start": far, "stop": far + timedelta(hours=1)})
        self.assertEqual(self._links(self._attendee()).date_to, month_after)
        soon = fields.Datetime.now().replace(microsecond=0) + timedelta(days=5)
        self.event.write({"start": soon, "stop": soon + timedelta(hours=1)})
        self.assertEqual(
            self._links(self._attendee()).date_to, soon + timedelta(hours=1, days=30)
        )

    def test_a_token_answers_its_own_invitation_only(self):
        token = self._attendee().sudo().access_token
        self.authenticate(None, None)
        url = "/calendar/meeting/accept?token=%s&id=%d"
        self.assertEqual(self.url_open(url % (token, self.event.id)).status_code, 200)
        self.assertEqual(
            self.url_open(url % (token, self.other_event.id)).status_code, 404
        )
        self._links(self._attendee()).sudo().date_to = (
            fields.Datetime.now() - timedelta(seconds=1)
        )
        self.assertEqual(
            self.url_open(url % (token, self.event.id)).status_code, 404, "expired"
        )

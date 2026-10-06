from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import users

from odoo.addons.website_event.tests.common import TestEventOnlineCommon


class TestTrackPushSecurity(TestEventOnlineCommon):
    @users("user_eventmanager")
    def test_track_social_security(self):
        track_1 = self.env["event.track"].create(
            {
                "name": "Track",
                "event_id": self.event_0.id,
                "date": fields.Datetime.now() + relativedelta(hours=2),
                "push_reminder": True,
                "push_reminder_delay": 10,
            }
        )

        push_reminder = (
            self.env["social.post"].sudo().search([("event_track_id", "=", track_1.id)])
        )
        self.assertEqual(1, len(push_reminder))
        self.assertEqual(
            "Your favorite track 'Track' will start in 10 minutes!",
            push_reminder.message,
        )

        track_1.write({"name": "New Name"})
        track_1.flush_recordset(["name", "date"])
        push_reminder = (
            self.env["social.post"].sudo().search([("event_track_id", "=", track_1.id)])
        )
        self.assertEqual(
            "Your favorite track 'New Name' will start in 10 minutes!",
            push_reminder.message,
        )

from datetime import timedelta

from odoo import fields
from odoo.db.schema import column_exists
from odoo.tests import TransactionCase, tagged

from odoo.addons.base.models.mixin_bearer_token import hash_bearer_token


@tagged("post_install", "-at_install")
class TestSealedEventToken(TransactionCase):
    def test_the_conference_token_is_kept_sealed(self):
        Event = self.env["calendar.event"]
        location = Event.get_discuss_videocall_location()
        token = location.rsplit("/", 1)[1]
        now = fields.Datetime.now()
        event = Event.create(
            {
                "name": "Weekly call",
                "start": now,
                "stop": now + timedelta(hours=1),
                "videocall_location": location,
                "access_token": token,
            }
        )

        self.assertFalse(column_exists(self.env.cr, "calendar_event", "access_token"))
        event.invalidate_recordset()
        self.assertEqual(event.access_token, token)
        self.assertEqual(event.access_token_hash, hash_bearer_token(token))
        self.assertIn(token, event.videocall_location)
        self.assertEqual(Event.sudo().search([("access_token", "=", token)]), event)
        event._update_access_token()
        self.assertNotEqual(event.access_token, token)
        self.assertFalse(Event.sudo().search([("access_token", "=", token)]))

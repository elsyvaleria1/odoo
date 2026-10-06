from odoo import Command
from odoo.tests.common import tagged

from odoo.addons.calendar.tests.booking.common import AppointmentCommon
from odoo.addons.website.tests.test_website_visitor import WebsiteVisitorTestsCommon


@tagged("website_visitor")
class TestCalendarEventVisitor(AppointmentCommon, WebsiteVisitorTestsCommon):
    def test_compute_email_phone(self):
        visitor = self.env["website.visitor"].create(
            {
                "access_token": "f9d2c6f3b024320ac31248595ac7fcb7",
            }
        )
        self.assertFalse(visitor.email or visitor.phone_ids)

        partner_0, partner_1 = self.env["res.partner"].create(
            [
                {
                    "name": "Test Customer 0",
                    "email": '"Test Customer 0" <calendar_event_0@test.example.com>',
                    "phone_ids": [
                        Command.create({"number": "+32456001120", "type": "mobile"})
                    ],
                },
                {
                    "name": "Test Customer 1",
                    "email": '"Test Customer 1" <calendar_event_1@test.example.com>',
                    "phone_ids": [
                        Command.create({"number": "+32456001121", "type": "mobile"})
                    ],
                },
            ]
        )

        self.env["calendar.event"].create(
            [
                {
                    "name": "Test event 0",
                    "appointment_booker_id": partner_0.id,
                    "visitor_id": visitor.id,
                },
                {
                    "name": "Test event 1",
                    "appointment_booker_id": partner_1.id,
                    "visitor_id": visitor.id,
                },
            ]
        )

        self.assertEqual(
            visitor.email, '"Test Customer 1" <calendar_event_1@test.example.com>'
        )
        self.assertEqual(visitor._phone_get_number().number, "+32456001121")

    def test_link_to_visitor_calendar_event(self):
        main_visitor, linked_visitor = self.env["website.visitor"].create(
            [self._prepare_main_visitor_data(), self._prepare_linked_visitor_data()]
        )
        all_calendar_events = (main_visitor + linked_visitor).calendar_event_ids
        linked_visitor._merge_visitor(main_visitor)

        self.assertEqual(len(main_visitor.calendar_event_ids), 2)
        self.assertEqual(main_visitor.calendar_event_ids, all_calendar_events)

        self.assertVisitorDeactivated(linked_visitor, main_visitor)

    def _prepare_main_visitor_data(self):
        values = super()._prepare_main_visitor_data()
        values.update(
            {"calendar_event_ids": [(0, 0, {"name": "Mitchel Main Calendar Event"})]}
        )
        return values

    def _prepare_linked_visitor_data(self):
        values = super()._prepare_linked_visitor_data()
        values.update(
            {
                "calendar_event_ids": [
                    (0, 0, {"name": "Mitchel Secondary Calendar Event"})
                ]
            }
        )
        return values

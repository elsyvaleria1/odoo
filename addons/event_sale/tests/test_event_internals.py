from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.fields import Datetime as FieldsDatetime
from odoo.tests.common import users

from odoo.addons.event_sale.tests.common import TestEventSaleCommon


class TestEventData(TestEventSaleCommon):
    @users("user_eventmanager")
    def test_event_configuration_from_type(self):
        event_type = self.event_type_tickets.with_user(self.env.user)
        self.assertEqual(
            event_type.event_type_ticket_ids.description,
            self.event_product.description_sale,
        )

        event = self.env["event.event"].create(
            {
                "name": "Event Update Type",
                "event_type_id": event_type.id,
                "date_begin": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=1)
                ),
                "date_end": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=15)
                ),
            }
        )

        event.write({"event_type_id": event_type.id})
        self.assertEqual(
            event.event_ticket_ids.name, event.event_type_id.event_type_ticket_ids.name
        )
        self.assertTrue(event.event_ticket_ids.seats_limited)
        self.assertEqual(event.event_ticket_ids.seats_max, 5)
        self.assertEqual(event.event_ticket_ids.product_id, self.event_product)
        self.assertEqual(event.event_ticket_ids.price, self.event_product.list_price)
        self.assertEqual(
            event.event_ticket_ids.description, self.event_product.description_sale
        )

    def test_event_registrable(self):
        event = self.event_0.with_user(self.env.user)
        self.assertTrue(event.event_registrations_open)

        ticket = self.env["event.event.ticket"].create(
            {
                "name": "TestTicket",
                "event_id": event.id,
                "product_id": self.event_product.id,
            }
        )
        self.assertTrue(event.event_registrations_open)

        ticket.product_id.action_archive()
        self.assertFalse(event.event_registrations_open)

        event_product = self.env["product.product"].create(
            {
                "name": "Test Registration Product New",
                "type": "service",
                "service_tracking": "event",
            }
        )
        new_ticket = self.env["event.event.ticket"].create(
            {
                "name": "TestTicket 2",
                "event_id": event.id,
                "product_id": event_product.id,
                "end_sale_datetime": FieldsDatetime.to_string(
                    datetime.now() + timedelta(days=2)
                ),
            }
        )
        self.assertTrue(new_ticket.sale_available)
        self.assertTrue(event.event_registrations_open)


class TestEventTicketData(TestEventSaleCommon):
    @freeze_time("2020-01-31 10:00:00")
    @users("user_eventmanager")
    def test_event_ticket_fields(self):
        event = self.event_0.with_user(self.env.user)
        event.write(
            {
                "event_ticket_ids": [
                    (5, 0),
                    (
                        0,
                        0,
                        {
                            "name": "First Ticket",
                            "product_id": self.event_product.id,
                            "seats_max": 30,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Second Ticket",
                            "product_id": self.event_product.id,
                            "start_sale_datetime": datetime(2020, 1, 10, 0, 0, 0),
                            "end_sale_datetime": datetime(2020, 2, 10, 23, 59, 59),
                        },
                    ),
                ],
            }
        )
        first_ticket = event.event_ticket_ids.filtered(
            lambda t: t.name == "First Ticket"
        )
        second_ticket = event.event_ticket_ids.filtered(
            lambda t: t.name == "Second Ticket"
        )
        second_ticket.write({"price": 8.0})

        self.assertEqual(first_ticket.price, self.event_product.list_price)
        self.assertEqual(second_ticket.price, 8.0)

        self.assertTrue(first_ticket.seats_limited)
        self.assertTrue(first_ticket.sale_available)
        self.assertFalse(first_ticket.is_expired)
        self.assertFalse(second_ticket.seats_limited)
        self.assertTrue(second_ticket.sale_available)
        self.assertFalse(second_ticket.is_expired)

        self.event_product.action_archive()
        self.assertFalse(first_ticket.sale_available)
        self.assertFalse(second_ticket.sale_available)

        self.event_product.action_unarchive()
        second_ticket.write({"end_sale_datetime": datetime(2020, 1, 20, 23, 59, 59)})
        self.assertFalse(second_ticket.sale_available)
        self.assertTrue(second_ticket.is_expired)
        second_ticket.write(
            {
                "start_sale_datetime": datetime(2020, 2, 10, 0, 0, 0),
                "end_sale_datetime": datetime(2020, 2, 20, 23, 59, 59),
            }
        )
        self.assertFalse(second_ticket.sale_available)
        self.assertFalse(second_ticket.is_expired)

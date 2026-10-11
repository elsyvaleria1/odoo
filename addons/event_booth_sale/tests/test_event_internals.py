from datetime import datetime, timedelta

from odoo import Command
from odoo.fields import Datetime as FieldsDatetime
from odoo.tests import Form, users

from odoo.addons.event_booth_sale.tests.common import TestEventBoothSaleCommon


class TestEventData(TestEventBoothSaleCommon):
    @users("user_eventmanager")
    def test_event_configuration_booths_from_type(self):
        event_type_nobooth = self.env["event.type"].create(
            {
                "name": "No booth",
            }
        )
        event_type_wbooths = self.env["event.type"].create(
            {
                "name": "Using booths",
                "event_type_booth_ids": [
                    Command.clear(),
                    Command.create(
                        {
                            "name": "Standard Booth",
                            "booth_category_id": self.event_booth_category_1.id,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Premium Booth",
                            "booth_category_id": self.event_booth_category_2.id,
                        }
                    ),
                ],
            }
        )

        event = self.env["event.event"].create(
            {
                "name": "Event",
                "date_begin": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=1)
                ),
                "date_end": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=15)
                ),
                "event_type_id": event_type_nobooth.id,
            }
        )
        self.assertEqual(event.event_booth_ids, self.env["event.booth"])

        event.write(
            {
                "event_booth_ids": [
                    Command.create(
                        {
                            "name": "Custom Standard Booth 1",
                            "booth_category_id": self.event_booth_category_1.id,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Custom Standard Booth 2",
                            "booth_category_id": self.event_booth_category_1.id,
                        }
                    ),
                ]
            }
        )
        self.assertEqual(event.event_booth_count, 2)
        self.assertEqual(event.event_booth_count_available, 2)
        self.assertEqual(event.event_booth_ids.product_id, self.event_booth_product)

        event.event_booth_ids[1].write({"partner_id": self.event_customer.id})
        self.assertEqual(event.event_booth_count, 2)
        self.assertEqual(event.event_booth_count_available, 2)
        self.assertEqual(
            event.event_booth_ids[1].message_partner_ids, self.env["res.partner"]
        )

        event.event_booth_ids[1].write({"state": "unavailable"})
        self.assertEqual(event.event_booth_count, 2)
        self.assertEqual(event.event_booth_count_available, 1)

        event.event_booth_ids[1].write({"partner_id": False})
        self.assertEqual(event.event_booth_count, 2)
        self.assertEqual(event.event_booth_count_available, 1)
        self.assertEqual(
            event.event_booth_ids[1].message_partner_ids, self.env["res.partner"]
        )

        self.user_eventmanager.write(
            {
                "group_ids": [
                    (4, self.env.ref("sale.group_sale_salesman").id),
                ]
            }
        )

        with Form(event) as event_form:
            event_form.event_type_id = event_type_wbooths
        self.assertEqual(event.event_booth_count, 3)
        self.assertEqual(
            {r["name"] for r in event.event_booth_ids},
            {"Custom Standard Booth 2", "Standard Booth", "Premium Booth"},
            "Should keep booths with reservation, remove unused ones and add type ones",
        )
        self.assertEqual(event.event_booth_count_available, 2)
        self.assertEqual(
            event.event_booth_category_ids,
            self.event_booth_category_1 + self.event_booth_category_2,
        )

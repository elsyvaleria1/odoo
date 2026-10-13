
from datetime import datetime

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBookingRelationOwnership(TransactionCase):
    def test_stale_relation_metadata_cleanup_preserves_booking_payload(self):
        resource = self.env["resource.resource"].create(
            {
                "type": "material",
                "name": "Upgrade payload resource",
                "capacity": 4,
            }
        )
        offer = self.env["appointment.type"].create(
            {
                "name": "Upgrade payload offer",
                "schedule_based_on": "resources",
                "resource_ids": [Command.set(resource.ids)],
            }
        )
        event = self.env["calendar.event"].create(
            {
                "name": "Upgrade payload booking",
                "appointment_type_id": offer.id,
                "start": datetime(2050, 1, 3, 10),
                "stop": datetime(2050, 1, 3, 11),
                "booking_line_ids": [
                    Command.create(
                        {
                            "resource_id": resource.id,
                            "capacity_reserved": 2,
                        }
                    )
                ],
            }
        )
        line = event.booking_line_ids
        relations = self.env["ir.model.relation"]
        legacy = relations.create(
            {
                "name": line._table,
                "model": self.env["ir.model"]._get_id("calendar.event"),
                "module": self.env.ref("base.module_calendar").id,
            }
        )
        relations._reflect_relations([], model_tables={line._table})
        self.assertFalse(legacy.exists())
        line.invalidate_recordset()
        self.assertEqual(line.capacity_reserved, 2)
        self.assertEqual(line.resource_id, resource)
        self.assertEqual(line.calendar_event_id, event)

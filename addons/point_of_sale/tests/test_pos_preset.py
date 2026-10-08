import logging

import odoo
from odoo.exceptions import ValidationError

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

_logger = logging.getLogger(__name__)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosPreset(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def test_an_attendance_may_end_at_midnight(self):
        calendar = self.env["resource.calendar"].create({"name": "AuditCal"})
        raised = None
        try:
            self.env["pos.preset"].create(
                {
                    "name": "AuditPreset",
                    "resource_calendar_id": calendar.id,
                    "attendance_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "Mon eve",
                                "dayofweek": "0",
                                "hour_from": 20.0,
                                "hour_to": 24.0,
                            },
                        )
                    ],
                }
            )
        except ValidationError as e:
            raised = e
        _logger.info("Attendance ending at midnight: raised=%r", raised)
        self.assertIsNone(
            raised,
            "a valid 20:00-24:00 attendance was rejected: %s" % raised,
        )

    def test_an_unused_slot_reports_an_empty_list(self):
        preset = self.env["pos.preset"].create({"name": "AuditPreset2"})
        usage = preset._get_slots_usage()
        _logger.info("Empty slot usage: %r", usage)
        self.assertEqual(usage["2099-01-01 12:00:00"], [])
        self.assertIsInstance(usage["2099-01-01 12:00:00"], list)

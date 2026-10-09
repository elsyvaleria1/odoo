import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Domain

_logger = logging.getLogger(__name__)

ACCESS_EVENT_MAP = {
    (5, 1): "access_granted",
    (5, 75): "access_granted",
    (5, 76): "access_denied",
    (5, 40): "access_granted",
    (5, 41): "access_denied",
    (5, 4): "access_granted",
    (5, 5): "access_denied",
    (5, 6): "access_granted",
    (5, 22): "access_denied",
    (5, 23): "access_granted",
    (5, 24): "access_granted",
    (5, 26): "door_event",
    (5, 2): "access_denied",
    (5, 3): "access_denied",
    (1, 0x404): "alarm",
    (1, 0x405): "alarm",
    (2, 0x400): "alarm",
    (5, 27): "alarm",
    (5, 28): "alarm",
}

RETENTION_DAYS = {
    "heartbeat": 7,
    "other": 90,
}
DEFAULT_RETENTION_DAYS = 90


class AccessEvent(models.Model):
    _name = "access.event"
    _description = "Access Event"
    _order = "event_time desc, id desc"

    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="device_id.company_id",
    )
    event_type = fields.Selection(
        selection=[
            ("access_granted", "Access Granted"),
            ("access_denied", "Access Denied"),
            ("door_event", "Door Event"),
            ("alarm", "Alarm"),
            ("heartbeat", "Heartbeat"),
            ("other", "Other"),
        ],
        index=True,
        required=True,
    )
    event_time = fields.Datetime(
        index=True,
        required=True,
    )
    event_data = fields.Text(
        string="Raw Event Data",
        help="Full event payload as JSON.",
    )
    major_type = fields.Integer(string="Major Event Type")
    sub_type = fields.Integer(string="Sub Event Type")
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        index=True,
        help="Matched via employee barcode = ISAPI employeeNoString.",
    )
    employee_no = fields.Char(
        index=True,
        help="employeeNoString from the device event.",
    )
    card_no = fields.Char(string="Card Number")
    person_name = fields.Char(help="Name reported by the device.")
    image = fields.Binary(
        string="Snapshot",
        attachment=True,
    )
    event_uid = fields.Char(
        string="Event UID",
        index=True,
        help="Unique identifier for deduplication (serialNo from device).",
    )
    attendance_status = fields.Char(
        help="Attendance status reported by device (checkIn, checkOut, etc.)."
    )

    # Partial on purpose: event_uid is what the device offers for
    # deduplication and an event without one cannot be deduplicated, so those
    # rows are exempt. A plain UNIQUE exempted them too, by PostgreSQL's NULL
    # rule rather than by saying so; this says so.
    _event_uid_uniq = models.UniqueIndex(
        "(device_id, event_uid) WHERE event_uid IS NOT NULL",
        "Duplicate event detected for this device!",
    )

    @api.model
    def _employee_for_badge(self, badge: str) -> int | None:
        # a badge is an employee's private identifier (hr.private), which no
        # privilege should open wide: the lookup elevates, and only the id of
        # the employee it names, in the reader's companies, leaves it
        employee = (
            self.env["hr.employee"]
            .sudo()
            .search(
                [("barcode", "=", badge), ("company_id", "in", self.env.companies.ids)],
                limit=1,
            )
        )
        return employee.id or None

    @api.model
    def map_event_type(self, major, sub):
        return ACCESS_EVENT_MAP.get((major, sub), "other")

    @api.autovacuum
    def _gc_access_events(self):
        now = fields.Datetime.now()
        expired = Domain.OR(
            [
                *(
                    Domain("event_type", "=", event_type)
                    & Domain("create_date", "<", now - timedelta(days=days))
                    for event_type, days in RETENTION_DAYS.items()
                ),
                Domain("event_type", "not in", list(RETENTION_DAYS))
                & Domain(
                    "create_date", "<", now - timedelta(days=DEFAULT_RETENTION_DAYS)
                ),
            ]
        )
        old_events = self.search(expired)
        for event_type, events in old_events.grouped("event_type").items():
            _logger.info(
                "Auto-vacuum: Removing %s old '%s' access events (>%s days)",
                len(events),
                event_type,
                RETENTION_DAYS.get(event_type, DEFAULT_RETENTION_DAYS),
            )
        old_events.unlink()
        return len(old_events)

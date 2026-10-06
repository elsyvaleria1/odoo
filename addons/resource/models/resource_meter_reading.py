from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.authority_keys import declare_authority_keys

declare_authority_keys("resource", "skip_meter_monotonic")


class ResourceMeterReading(models.Model):
    _name = "resource.meter.reading"
    _description = "Resource Meter Reading"
    _order = "date desc, id desc"

    meter_id = fields.Many2one(
        comodel_name="resource.meter",
        index=True,
        required=True,
        ondelete="cascade",
    )
    resource_id = fields.Many2one(
        related="meter_id.resource_id",
    )
    company_id = fields.Many2one(
        related="meter_id.company_id",
    )
    date = fields.Datetime(
        default=fields.Datetime.now,
        index=True,
        required=True,
    )
    value = fields.Float(required=True)
    source = fields.Selection(
        selection=[
            ("manual", "Manual"),
            ("telemetry", "Telemetry"),
            ("service", "Service"),
        ],
        default="manual",
        required=True,
    )
    note = fields.Char()

    _meter_date_idx = models.Index("(meter_id, date)")
    _value_positive = models.Constraint(
        "CHECK(value >= 0)", "A meter reading cannot be negative."
    )

    @api.constrains("value", "date", "meter_id")
    def _check_monotonic(self) -> None:
        if self.env.context.get("skip_meter_monotonic"):
            return
        for reading in self.filtered("meter_id.monotonic"):
            neighbours = reading.meter_id.reading_ids - reading
            before = neighbours.filtered_domain(
                [("date", "<=", reading.date), ("value", ">", reading.value)]
            )
            after = neighbours.filtered_domain(
                [("date", ">", reading.date), ("value", "<", reading.value)]
            )
            if before or after:
                raise ValidationError(
                    self.env._(
                        "%(meter)s: a reading of %(value)s on %(date)s would make the meter run backwards.",
                        meter=reading.meter_id.display_name,
                        value=reading.value,
                        date=reading.date,
                    )
                )

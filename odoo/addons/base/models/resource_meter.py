from odoo import api, fields, models
from odoo.tools import SQL


class ResourceMeter(models.Model):
    _name = "resource.meter"
    _description = "Resource Meter"
    _order = "resource_id, sequence, id"

    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="resource_id.company_id",
    )
    name = fields.Char(
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=10)
    kind = fields.Selection(
        selection=[
            ("odometer", "Odometer"),
            ("hours", "Running Hours"),
            ("cycles", "Cycles"),
        ],
        default="odometer",
        required=True,
    )
    uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
    )
    monotonic = fields.Boolean(
        default=True,
        help="A reading below the previous one is rejected: an odometer only goes up.",
    )
    reading_ids = fields.One2many(
        comodel_name="resource.meter.reading",
        inverse_name="meter_id",
    )
    last_reading_id = fields.Many2one(
        comodel_name="resource.meter.reading",
        compute="_compute_last_reading_id",
        store=True,
    )
    value = fields.Float(
        related="last_reading_id.value",
        string="Current Value",
    )
    date = fields.Datetime(
        related="last_reading_id.date",
        string="Read On",
    )

    _resource_kind_uniq = models.Constraint(
        "UNIQUE(resource_id, kind)", "A resource carries one meter of each kind."
    )

    @api.depends("reading_ids.date", "reading_ids.value")
    def _compute_last_reading_id(self) -> None:
        Reading = self.env["resource.meter.reading"]
        latest = {}
        if stored := self.filtered("id"):
            Reading.flush_model(["meter_id", "date"])
            self.env.cr.execute(
                SQL(
                    "SELECT DISTINCT ON (meter_id) meter_id, id"
                    " FROM resource_meter_reading WHERE meter_id = ANY(%s)"
                    " ORDER BY meter_id, date DESC, id DESC",
                    stored.ids,
                )
            )
            latest = dict(self.env.cr.fetchall())
        for meter in self:
            if meter.id:
                meter.last_reading_id = Reading.browse(latest.get(meter.id))
            else:
                meter.last_reading_id = meter.reading_ids.sorted(
                    key=lambda r: (r.date, r.id), reverse=True
                )[:1]

    def record(self, value, date=None, source=None):
        self.check_singleton()
        return self.env["resource.meter.reading"].create(
            {
                "meter_id": self.id,
                "value": value,
                "date": date or fields.Datetime.now(),
                "source": source or "manual",
            }
        )

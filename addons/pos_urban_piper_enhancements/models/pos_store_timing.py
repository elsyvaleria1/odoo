from odoo import fields, models


class PosStoreTiming(models.Model):
    _name = "pos.store.timing"
    _description = "Pos Store Timings"

    weekday = fields.Selection(
        selection=[
            ("monday", "Monday"),
            ("tuesday", "Tuesday"),
            ("wednesday", "Wednesday"),
            ("thursday", "Thursday"),
            ("friday", "Friday"),
            ("saturday", "Saturday"),
            ("sunday", "Sunday"),
        ],
        string="Week Day",
        default="monday",
        required=True,
    )
    start_hour = fields.Float(
        string="Starting Hour",
        default=8.0,
        required=True,
    )
    end_hour = fields.Float(
        string="Ending Hour",
        default=17.0,
        required=True,
    )
    config_ids = fields.Many2many(
        comodel_name="pos.config",
        string="Point of Sale accociated to this timing",
    )

    _check_start_and_end_hour = models.Constraint(
        "CHECK(start_hour < end_hour)",
        "The end time must be later than the start time.",
    )

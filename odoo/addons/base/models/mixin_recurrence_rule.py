from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.base.models.mixin_recurrence_interval import (
    REPEAT_UNIT_SELECTION as REPEAT_UNIT_SELECTION,  # noqa: PLC0414 -- Explicit public re-export for callers of this module.
)

REPEAT_TYPE_SELECTION = [
    ("forever", "Forever"),
    ("until", "Until"),
]

REPEAT_TYPE_COUNT = ("count", "Number of Repetitions")

WEEKDAY_SELECTION = [
    ("MON", "Monday"),
    ("TUE", "Tuesday"),
    ("WED", "Wednesday"),
    ("THU", "Thursday"),
    ("FRI", "Friday"),
    ("SAT", "Saturday"),
    ("SUN", "Sunday"),
]


class MixinRecurrenceRule(models.AbstractModel):
    _name = "mixin.recurrence.rule"
    _description = "Recurrence Rule Mixin"
    _inherit = ["mixin.recurrence.interval"]

    repeat_type = fields.Selection(
        selection=REPEAT_TYPE_SELECTION,
        string="Until",
        export_string_translation=False,
        default="forever",
    )
    repeat_until = fields.Date(string="End Date")

    def _is_repeat_until_required(self) -> bool:
        self.check_singleton()
        return self.repeat_type == "until"

    @api.constrains("repeat_type", "repeat_until")
    def _check_repeat_until(self) -> None:
        if self.filtered(
            lambda rule: rule._is_repeat_until_required() and not rule.repeat_until
        ):
            raise ValidationError(
                self.env._("A recurrence that repeats until a date needs that date.")
            )

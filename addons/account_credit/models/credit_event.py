from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import frozendict

SEVERITIES = [
    ("info", "Information"),
    ("warning", "Warning"),
    ("critical", "Critical"),
]


class CreditEventType(models.Model):
    _name = "credit.event.type"
    _inherit = ["mixin.catalog"]
    _description = "Credit Event Type"
    _order = "sequence, id"

    _code_uniq = models.UniqueIndex("(code)")

    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    severity = fields.Selection(
        selection=SEVERITIES,
        default="info",
        required=True,
    )
    is_hold = fields.Boolean(
        help="An event of this type blocks every credit operation of the profile "
        "until it is lifted.",
    )
    requires_review = fields.Boolean(
        help="Recording this event opens a review of the profile.",
    )
    grade_cap_id = fields.Many2one(
        comodel_name="credit.grade",
        help="While an event of this type is open, the profile's grade is no "
        "better than this one.",
    )


class CreditEvent(models.Model):
    _name = "credit.event"
    _inherit = ["mixin.mail.thread"]
    _description = "Credit Event"
    _order = "date desc, id desc"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    profile_id = fields.Many2one(
        comodel_name="credit.profile",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(related="profile_id.company_id")
    partner_id = fields.Many2one(related="profile_id.partner_id")
    currency_id = fields.Many2one(related="company_id.currency_id")
    type_id = fields.Many2one(
        comodel_name="credit.event.type",
        index=True,
        required=True,
    )
    code = fields.Char(related="type_id.code")
    severity = fields.Selection(related="type_id.severity")
    is_hold = fields.Boolean(related="type_id.is_hold")
    date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )
    amount = fields.Monetary(currency_field="currency_id")
    note = fields.Text()
    res_model = fields.Char()
    res_id = fields.Integer()
    user_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.user,
    )
    grade_from_id = fields.Many2one(
        comodel_name="credit.grade",
        help="Grade the profile left, on a grade change.",
    )
    grade_to_id = fields.Many2one(
        comodel_name="credit.grade",
        help="Grade the profile entered, on a grade change.",
    )
    lifted_on = fields.Datetime(tracking=True)
    lifted_by_id = fields.Many2one(comodel_name="res.users")
    is_open = fields.Boolean(
        compute="_compute_is_open",
        store=True,
    )

    @api.depends("lifted_on")
    def _compute_is_open(self) -> None:
        for event in self:
            event.is_open = not event.lifted_on

    @api.depends("type_id", "partner_id")
    def _compute_display_name(self):
        for event in self:
            event.display_name = f"{event.type_id.name}: {event.partner_id.name}"

    def action_lift(self) -> None:
        open_events = self.filtered("is_open")
        if not open_events:
            return
        if not self.env.user.has_group("account_credit.group_credit_manager"):
            raise ValidationError(
                self.env._("Only a credit manager can lift a credit event.")
            )
        open_events.write(
            {"lifted_on": fields.Datetime.now(), "lifted_by_id": self.env.user.id}
        )
        open_events.profile_id._on_events_changed()

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        events.profile_id._on_events_changed()
        for event in events.filtered("type_id.requires_review"):
            event.profile_id._open_review("event", trigger_event=event)
        return events

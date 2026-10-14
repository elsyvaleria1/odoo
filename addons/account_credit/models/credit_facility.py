from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import frozendict

FACILITY_SOURCES = [
    ("grade", "Grade-based line"),
    ("manual", "Manually granted line"),
    ("authorization", "Authorization of an excess on orders"),
    ("insurance", "Credit insurance"),
]
FACILITY_STATES = [
    ("draft", "Draft"),
    ("active", "Active"),
    ("expired", "Expired"),
    ("revoked", "Revoked"),
]


class CreditFacility(models.Model):
    _name = "credit.facility"
    _inherit = ["mixin.mail.thread"]
    _description = "Credit Facility"
    _order = "date_start desc, id desc"

    _positive_amount = models.Constraint(
        "CHECK(amount > 0)",
        "A facility grants a positive amount.",
    )
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    profile_id = fields.Many2one(
        comodel_name="credit.profile",
        index=True,
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        related="profile_id.partner_id",
        store=True,
    )
    company_id = fields.Many2one(
        related="profile_id.company_id",
        store=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    source = fields.Selection(
        selection=FACILITY_SOURCES,
        default="manual",
        required=True,
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    date_start = fields.Date(
        default=fields.Date.today,
        required=True,
    )
    date_end = fields.Date(
        tracking=True,
        help="Last day the line is granted. Empty means until revoked.",
    )
    state = fields.Selection(
        selection=FACILITY_STATES,
        default="active",
        required=True,
        tracking=True,
    )
    active = fields.Boolean(
        compute="_compute_active",
        inverse="_inverse_active",
        search="_search_active",
        help="Granting or waiting to grant. Clearing it revokes the line; the "
        "record stays so the decision remains auditable.",
    )
    order_ids = fields.Many2many(
        comodel_name="sale.order",
        relation="credit_facility_sale_order_rel",
        column1="facility_id",
        column2="order_id",
        check_company=True,
        help="Orders whose excess over the limit this authorization covered. It "
        "grants while any of them is still open: neither cancelled nor fully "
        "invoiced, since a posted invoice moves the excess into the receivable.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Granted by",
        default=lambda self: self.env.user,
        required=True,
    )
    review_id = fields.Many2one(
        comodel_name="credit.review",
        ondelete="set null",
    )
    reason = fields.Char()

    @api.depends("state")
    def _compute_active(self) -> None:
        for facility in self:
            facility.active = facility.state in ("draft", "active")

    def _inverse_active(self) -> None:
        for facility in self:
            if facility.active and facility.state == "revoked":
                facility.state = "active"
            elif not facility.active and facility.state in ("draft", "active"):
                facility.state = "revoked"
        self.profile_id._on_facilities_changed()

    def _search_active(self, operator, value) -> list:
        wanted = ("draft", "active")
        values = value if isinstance(value, (list, tuple, set)) else [value]
        truthy = any(values)
        positive = (operator in ("=", "in")) == truthy
        return [("state", "in" if positive else "not in", wanted)]

    @api.depends("partner_id", "amount", "source")
    def _compute_name(self):
        sources = dict(self._fields["source"]._description_selection(self.env))
        for facility in self:
            facility.name = "%s: %s %s" % (
                facility.partner_id.name or "",
                sources.get(facility.source, ""),
                facility.currency_id.format(facility.amount)
                if facility.currency_id
                else facility.amount,
            )

    @api.constrains("date_start", "date_end")
    def _check_dates(self) -> None:
        for facility in self:
            if facility.date_end and facility.date_end < facility.date_start:
                raise ValidationError(
                    self.env._("A facility cannot end before it starts.")
                )

    def _is_granting(self, today=None) -> bool:
        self.check_singleton()
        today = today or fields.Date.today()
        if self.state != "active" or self.date_start > today:
            return False
        if self.date_end and self.date_end < today:
            return False
        if self.source == "authorization" and self.order_ids:
            return any(
                order._is_credit_authorization_open() for order in self.order_ids
            )
        return True

    def action_revoke(self):
        self.filtered(lambda f: f.state in ("draft", "active")).write(
            {"state": "revoked"}
        )
        self.profile_id._on_facilities_changed()

    def action_activate(self):
        self.filtered(lambda f: f.state == "draft").write({"state": "active"})
        self.profile_id._on_facilities_changed()

    @api.model
    def _cron_expire(self):
        today = fields.Date.today()
        expired = self.search([("state", "=", "active"), ("date_end", "<", today)])
        if not expired:
            return
        expired.write({"state": "expired"})
        expired.profile_id._on_facilities_changed()
        amounts = {}
        for facility in expired:
            amounts[facility.profile_id] = (
                amounts.get(facility.profile_id, 0.0) + facility.amount
            )
        expired.profile_id._record_event("facility_expired", amount_by_profile=amounts)

    @api.model_create_multi
    def create(self, vals_list):
        facilities = super().create(vals_list)
        facilities.profile_id._on_facilities_changed()
        return facilities

    def write(self, vals):
        result = super().write(vals)
        if {"amount", "state", "date_start", "date_end", "order_ids"} & set(vals):
            self.profile_id._on_facilities_changed()
        return result

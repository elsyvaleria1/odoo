from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict
from odoo.tools.misc import formatLang


class EventEventTicket(models.Model):
    _name = "event.event.ticket"
    _access_anchors = frozendict({"company": "event_id.company_id"})
    _inherit = ["event.type.ticket"]
    _description = "Event Ticket"
    _order = "event_id, sequence, name, id"

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if (
            "name" in fields
            and (not res.get("name") or res["name"] == self.env._("Registration"))
            and self.env.context.get("default_event_name")
        ):
            res["name"] = self.env._(
                "Registration for %s", self.env.context["default_event_name"]
            )
        return res

    event_type_id = fields.Many2one(
        required=False,
        ondelete="set null",
    )
    event_id = fields.Many2one(
        comodel_name="event.event",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="event_id.company_id",
    )
    start_sale_datetime = fields.Datetime(string="Registration Start")
    end_sale_datetime = fields.Datetime(string="Registration End")
    is_launched = fields.Boolean(
        string="Are sales launched",
        compute="_compute_is_launched",
    )
    is_expired = fields.Boolean(compute="_compute_is_expired")
    sale_available = fields.Boolean(
        string="Is Available",
        compute="_compute_sale_available",
        compute_sudo=True,
        help="Whether it is possible to sell these tickets",
    )
    registration_ids = fields.One2many(
        comodel_name="event.registration",
        inverse_name="event_ticket_id",
        string="Registrations",
    )
    seats_reserved = fields.Integer(
        string="Reserved Seats",
        compute="_compute_seats",
        store=False,
    )
    seats_available = fields.Integer(
        string="Available Seats",
        compute="_compute_seats",
        store=False,
    )
    seats_used = fields.Integer(
        string="Used Seats",
        compute="_compute_seats",
        store=False,
    )
    seats_taken = fields.Integer(
        string="Taken Seats",
        compute="_compute_seats",
        store=False,
        aggregator="sum",
    )
    limit_max_per_order = fields.Integer(
        string="Limit per Order",
        default=0,
        help="Maximum of this product per order.\nSet to 0 to ignore this rule",
    )
    is_sold_out = fields.Boolean(
        string="Sold Out",
        compute="_compute_is_sold_out",
        help="Whether seats are not available for this ticket.",
    )
    color = fields.Char(default="#875A7B")

    @api.depends("end_sale_datetime")
    def _compute_is_expired(self) -> None:
        now = fields.Datetime.now()
        for ticket in self:
            ticket.is_expired = bool(
                ticket.end_sale_datetime and ticket.end_sale_datetime < now
            )

    @api.depends("start_sale_datetime")
    def _compute_is_launched(self) -> None:
        now = fields.Datetime.now()
        for ticket in self:
            ticket.is_launched = (
                not ticket.start_sale_datetime or ticket.start_sale_datetime <= now
            )

    @api.depends("is_expired", "is_launched", "is_sold_out")
    def _compute_sale_available(self) -> None:
        for ticket in self:
            ticket.sale_available = (
                ticket.is_launched and not ticket.is_expired and not ticket.is_sold_out
            )

    @api.depends("seats_max", "registration_ids.state", "registration_ids.active")
    def _compute_seats(self) -> None:
        base_vals = {"seats_reserved": 0, "seats_used": 0}
        results = self.env["event.registration"]._count_taken_seats_by(
            "event_ticket_id", self.ids
        )
        for ticket in self:
            ticket.seats_available = 0
            ticket.update(results.get(ticket._origin.id or ticket.id, base_vals))
            if ticket.seats_max > 0:
                ticket.seats_available = ticket.seats_max - (
                    ticket.seats_reserved + ticket.seats_used
                )
            ticket.seats_taken = ticket.seats_reserved + ticket.seats_used

    @api.depends(
        "seats_limited", "seats_available", "event_id.event_registrations_sold_out"
    )
    def _compute_is_sold_out(self) -> None:
        for ticket in self:
            ticket.is_sold_out = (
                ticket.seats_limited and not ticket.seats_available
            ) or ticket.event_id.event_registrations_sold_out

    @api.constrains("start_sale_datetime", "end_sale_datetime")
    def _check_dates_coherency(self) -> None:
        for ticket in self:
            if (
                ticket.start_sale_datetime
                and ticket.end_sale_datetime
                and ticket.start_sale_datetime > ticket.end_sale_datetime
            ):
                raise UserError(
                    self.env._(
                        "The stop date cannot be earlier than the start date. "
                        "Please check ticket %(ticket_name)s",
                        ticket_name=ticket.name,
                    )
                )

    @api.constrains("limit_max_per_order", "seats_max")
    def _check_limit_max_per_order(self) -> None:
        for ticket in self:
            if ticket.seats_max and ticket.limit_max_per_order > ticket.seats_max:
                raise UserError(
                    self.env._(
                        "The limit per order cannot be greater than the maximum seats number. "
                        "Please check ticket %(ticket_name)s",
                        ticket_name=ticket.name,
                    )
                )
            if ticket.limit_max_per_order > ticket.event_id.EVENT_MAX_TICKETS:
                raise UserError(
                    self.env._(
                        "The limit per order cannot be greater than %(limit_orderable)s. "
                        "Please check ticket %(ticket_name)s",
                        limit_orderable=ticket.event_id.EVENT_MAX_TICKETS,
                        ticket_name=ticket.name,
                    )
                )
            if ticket.limit_max_per_order < 0:
                raise UserError(
                    self.env._(
                        "The limit per order must be positive. "
                        "Please check ticket %(ticket_name)s",
                        ticket_name=ticket.name,
                    )
                )

    @api.depends("seats_max", "seats_available")
    @api.depends_context("name_with_seats_availability")
    def _compute_display_name(self):
        if not self.env.context.get("name_with_seats_availability"):
            return super()._compute_display_name()
        for ticket in self:
            if not ticket.seats_max or ticket.event_id.is_multi_slots:
                name = ticket.name
            elif not ticket.seats_available:
                name = self.env._("%(ticket_name)s (Sold out)", ticket_name=ticket.name)
            else:
                name = self.env._(
                    "%(ticket_name)s (%(count)s seats remaining)",
                    ticket_name=ticket.name,
                    count=formatLang(self.env, ticket.seats_available, digits=0),
                )
            ticket.display_name = name
        return None

    def _get_current_limit_per_order(self, event_slot=False, event=False):
        if event_slot:
            event_slot.check_singleton()
        if self:
            slots_seats_available = self.event_id._get_seats_availability(
                [[event_slot, ticket] for ticket in self]
            )
        else:
            return {
                False: event_slot.seats_available
                if event_slot
                else (
                    event.seats_available
                    if event.seats_limited
                    else event.EVENT_MAX_TICKETS
                )
            }
        availabilities = {}
        for ticket, seats_available in zip(self, slots_seats_available, strict=True):
            if seats_available is None:
                seats_available = (
                    ticket.limit_max_per_order or ticket.event_id.EVENT_MAX_TICKETS
                )
            else:
                seats_available = min(
                    ticket.limit_max_per_order or seats_available, seats_available
                )
            availabilities[ticket.id] = seats_available
        return availabilities

    def _get_ticket_multiline_description(self):
        return "%s\n%s" % (self.display_name, self.event_id.display_name)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_if_registrations(self) -> None:
        blocking = self.filtered("registration_ids")
        if blocking:
            raise UserError(
                self.env._(
                    "The following tickets cannot be deleted while they have one or more registrations linked to them:\n- %s",
                    "\n- ".join(blocking.mapped("name")),
                )
            )

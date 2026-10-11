import ast
import hashlib
import logging

from odoo import api, fields, models
from odoo.tools import frozendict

_logger = logging.getLogger(__name__)


class DAVCalendar(models.Model):
    _name = "dav.calendar"
    _description = "DAV Calendar Collection"
    _order = "sequence, name"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    name = fields.Char(
        string="Calendar Name",
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Owner",
        default=lambda self: self.env.user,
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
    )

    collection_uid = fields.Char(
        string="Collection UID",
        index=True,
        copy=False,
        readonly=True,
        required=True,
    )
    ctag = fields.Char(
        string="Collection Tag",
        compute="_compute_ctag",
        store=False,
        help="Changes when any event in collection is modified (always computed fresh)",
    )

    color = fields.Char(
        default="#3a87ad",
        help="Calendar color for client display (hex format)",
    )
    event_domain = fields.Text(
        string="Event Filter",
        default="[]",
        help="Odoo domain to filter events in this calendar",
    )
    include_shared_events = fields.Boolean(
        default=True,
        help="Include events where user is a participant",
    )

    event_count = fields.Integer(compute="_compute_ctag")

    @api.depends("name", "user_id")
    def _compute_display_name(self):
        for calendar in self:
            calendar.display_name = f"{calendar.name} ({calendar.user_id.name})"

    @api.depends("user_id", "event_domain", "include_shared_events")
    def _compute_ctag(self) -> None:
        Event = self.env["calendar.event"].with_context(active_test=False)
        for calendar in self:
            [(count, latest)] = Event._read_group(  # noqa: E8507 -- each calendar counts its own domain
                calendar._get_domain_event(),
                aggregates=["__count", "write_date:max"],
            )
            calendar.event_count = count
            calendar.ctag = (
                hashlib.md5(f"{count}-{latest}".encode()).hexdigest()[:16]
                if count
                else "empty"
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "collection_uid" not in vals:
                seq = self.env["ir.sequence"].next_by_code("dav.collection.uid")
                vals["collection_uid"] = f"calendar-{seq}"
        return super().create(vals_list)

    @api.model
    def _provision_default_calendars(self, user) -> None:
        if self.search_count([("user_id", "=", user.id)], limit=1):
            return
        self.create(
            {
                "name": "My Calendar",
                "user_id": user.id,
                "company_id": user.company_id.id,
                "include_shared_events": True,
            }
        )

    def _get_domain_event(self, date_from=None, date_to=None):
        self.check_singleton()

        try:
            domain = ast.literal_eval(self.event_domain or "[]")
            if not isinstance(domain, list):
                _logger.warning(
                    "Invalid event_domain in calendar %s: Expected list, got %s",
                    self.id,
                    type(domain).__name__,
                )
                domain = []
        except (ValueError, SyntaxError) as e:
            _logger.warning("Invalid event_domain in calendar %s: %s", self.id, e)
            domain = []

        if self.include_shared_events:
            domain.extend(
                [
                    "|",
                    ("user_id", "=", self.user_id.id),
                    ("partner_ids", "in", self.user_id.partner_id.id),
                ]
            )
        else:
            domain.append(("user_id", "=", self.user_id.id))

        if date_from:
            domain.append(("stop", ">=", date_from))
        if date_to:
            domain.append(("start", "<=", date_to))

        return domain

    def get_events(self, date_from=None, date_to=None):
        self.check_singleton()
        domain = self._get_domain_event(date_from, date_to)
        return self.env["calendar.event"].search(domain)

    def action_view_events(self) -> dict:
        self.check_singleton()
        domain = self._get_domain_event()
        return {
            "type": "ir.actions.act_window",
            "name": f"{self.name} - Events",
            "res_model": "calendar.event",
            "view_mode": "calendar,list,form",
            "domain": domain,
            "context": {"default_user_id": self.user_id.id},
        }

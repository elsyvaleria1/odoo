from collections import defaultdict

from dateutil.relativedelta import relativedelta
from lxml import html

from odoo import api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.tools import LazyTranslate, html_sanitize

from odoo.addons.web.controllers.utils import clean_action

_lt = LazyTranslate(__name__)

TICKET_PRIORITY = [
    ("0", "Low priority"),
    ("1", "Medium priority"),
    ("2", "High priority"),
    ("3", "Urgent"),
]


class HelpdeskTicket(models.Model):
    _name = "helpdesk.ticket"
    _description = "Helpdesk Ticket"
    _order = "priority desc, id desc"
    _mail_defaults_to_email = True
    _mail_thread_customer = True
    _primary_email = "partner_email"
    _inherit = [
        "mixin.portal",
        "mixin.mail.thread.cc",
        "mixin.utm",
        "mixin.rating",
        "mixin.mail.activity",
        "mixin.mail.tracking.duration",
    ]
    _track_duration_field = "stage_id"

    @api.model
    def default_get(self, fields):
        result = self.env["team.team"]._drop_default_of_other_usage(
            super().default_get(fields), "helpdesk"
        )
        if "team_id" in fields and "team_id" not in result:
            result["team_id"] = self._default_team_id()
        if result.get("team_id") and fields:
            team = self.env["team.team"].browse(result["team_id"])
            if "stage_id" in fields and "stage_id" not in result:
                result["stage_id"] = team._get_stage()[team.id].id
            if (
                "user_id" in fields
                and "user_id" not in result
                and (
                    "stage_id" in fields
                    and not self.env["helpdesk.stage"].browse(result["stage_id"]).fold
                )
            ):
                result["user_id"] = team._get_user_to_assign({team: 1})[team.id][0]
        return result

    def _default_team_id(self):
        team_id = (
            self.env["team.team"]
            .search(
                [("use_helpdesk", "=", True), ("member_ids", "in", self.env.uid)],
                limit=1,
            )
            .id
        )
        if not team_id:
            team_id = (
                self.env["team.team"].search([("use_helpdesk", "=", True)], limit=1).id
            )
        return team_id

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        search_domain = [("id", "in", stages.ids)]
        if self.env.context.get("default_team_id"):
            search_domain = [
                "|",
                ("team_ids", "in", self.env.context["default_team_id"]),
            ] + search_domain

        return stages.search(search_domain)

    name = fields.Char(
        string="Subject",
        index=True,
        required=True,
        tracking=True,
    )
    team_id = fields.Many2one(
        comodel_name="team.team",
        string="Helpdesk Team",
        default=lambda self: self._default_team_id(),
        index=True,
        domain=[("use_helpdesk", "=", True)],
        tracking=True,
    )
    use_sla = fields.Boolean(related="team_id.helpdesk_use_sla")
    team_privacy_visibility = fields.Selection(
        related="team_id.helpdesk_privacy_visibility",
        export_string_translation=False,
    )
    description = fields.Html(sanitize_attributes=False)
    active = fields.Boolean(default=True)
    tag_ids = fields.Many2many(
        comodel_name="helpdesk.tag",
        string="Tags",
    )
    company_id = fields.Many2one(
        related="team_id.company_id",
        string="Company",
        readonly=True,
    )
    color = fields.Integer(string="Color Index")
    kanban_state = fields.Selection(
        selection=[
            ("normal", "In progress"),
            ("done", "Ready"),
            ("blocked", "Blocked"),
        ],
        default="normal",
        copy=False,
        required=True,
    )
    kanban_state_label = fields.Char(
        compute="_compute_kanban_state_label",
        tracking=True,
    )
    legend_blocked = fields.Char(
        related="stage_id.legend_blocked",
        string="Kanban Blocked Explanation",
        related_sudo=False,
        readonly=True,
    )
    legend_done = fields.Char(
        related="stage_id.legend_done",
        string="Kanban Valid Explanation",
        related_sudo=False,
        readonly=True,
    )
    legend_normal = fields.Char(
        related="stage_id.legend_normal",
        string="Kanban Ongoing Explanation",
        related_sudo=False,
        readonly=True,
    )
    domain_user_ids = fields.Many2many(
        comodel_name="res.users",
        export_string_translation=False,
        compute="_compute_domain_user_ids",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Assigned to",
        compute="_compute_user_and_stage_ids",
        store=True,
        readonly=False,
        falsy_value_label=_lt("👤 Unassigned"),
        domain=lambda self: [
            ("all_group_ids", "in", self.env.ref("helpdesk.group_helpdesk_user").id)
        ],
        tracking=True,
    )
    properties = fields.Properties(
        definition="team_id.ticket_properties",
        copy=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        index=True,
        tracking=True,
    )
    partner_ticket_ids = fields.Many2many(
        comodel_name="helpdesk.ticket",
        string="Partner Tickets",
        compute="_compute_partner_ticket_count",
    )
    partner_ticket_count = fields.Integer(
        string="Number of other tickets from the same partner",
        compute="_compute_partner_ticket_count",
    )
    partner_open_ticket_count = fields.Integer(
        string="Number of other open tickets from the same partner",
        compute="_compute_partner_ticket_count",
    )
    partner_name = fields.Char(
        string="Customer Name",
        compute="_compute_partner_name",
        store=True,
        readonly=False,
    )
    partner_email = fields.Char(
        string="Customer Email",
        compute="_compute_partner_email",
        inverse="_inverse_partner_email",
        store=True,
        readonly=False,
    )
    phone_ids = fields.Many2many(
        comodel_name="phone.number",
        relation="helpdesk_ticket_phone_number_rel",
        column1="ticket_id",
        column2="phone_number_id",
        string="Customer Phone",
        compute="_compute_phone_ids",
        inverse="_inverse_phone_ids",
        store=True,
        copy=False,
        readonly=False,
    )
    commercial_partner_id = fields.Many2one(related="partner_id.commercial_partner_id")
    closed_by_partner = fields.Boolean(
        string="Closed by Partner",
        readonly=True,
    )
    priority = fields.Selection(
        selection=TICKET_PRIORITY,
        default="0",
        tracking=True,
    )
    stage_id = fields.Many2one(
        comodel_name="helpdesk.stage",
        compute="_compute_user_and_stage_ids",
        store=True,
        index=True,
        copy=False,
        readonly=False,
        group_expand="_read_group_stage_ids",
        domain="[('team_ids', '=', team_id)]",
        ondelete="restrict",
        tracking=1,
    )
    stage_id_color = fields.Integer(
        related="stage_id.color",
        string="Stage Color",
        export_string_translation=False,
    )
    fold = fields.Boolean(
        related="stage_id.fold",
        export_string_translation=False,
    )
    date_last_stage_update = fields.Datetime(
        string="Last Stage Update",
        copy=False,
        readonly=True,
    )
    ticket_ref = fields.Char(
        string="Ticket IDs Sequence",
        index=True,
        copy=False,
        readonly=True,
        order_by_field="id",
    )
    assign_date = fields.Datetime(string="First assignment date")
    assign_hours = fields.Float(
        string="Time to first assignment (hours)",
        compute="_compute_assign_hours",
        store=True,
        aggregator="avg",
    )
    close_date = fields.Datetime(
        string="Close date",
        copy=False,
    )
    close_hours = fields.Float(
        string="Time to close (hours)",
        compute="_compute_close_hours",
        store=True,
        aggregator="avg",
    )
    open_hours = fields.Integer(
        string="Open Time (hours)",
        compute="_compute_open_hours",
        search="_search_open_hours",
        aggregator="avg",
    )
    sla_ids = fields.Many2many(
        comodel_name="helpdesk.sla",
        relation="helpdesk_sla_status",
        column1="ticket_id",
        column2="sla_id",
        string="SLAs",
        copy=False,
    )
    sla_status_ids = fields.One2many(
        comodel_name="helpdesk.sla.status",
        inverse_name="ticket_id",
        string="SLA Status",
    )
    sla_reached_late = fields.Boolean(
        string="Has SLA reached late",
        compute="_compute_sla_reached_late",
        compute_sudo=True,
        store=True,
    )
    sla_reached = fields.Boolean(
        string="Has SLA reached",
        compute="_compute_sla_reached",
        compute_sudo=True,
        store=True,
    )
    sla_deadline = fields.Datetime(
        string="SLA Deadline",
        compute="_compute_sla_deadline",
        compute_sudo=True,
        store=True,
        falsy_value_label=_lt("Deadline reached"),
    )
    sla_deadline_hours = fields.Float(
        string="Working Hours until SLA Deadline",
        compute="_compute_sla_deadline",
        compute_sudo=True,
        store=True,
        aggregator="avg",
    )
    sla_fail = fields.Boolean(
        string="Failed SLA Policy",
        compute="_compute_sla_fail",
        search="_search_sla_fail",
    )
    sla_success = fields.Boolean(
        string="Success SLA Policy",
        compute="_compute_sla_success",
        search="_search_sla_success",
    )

    use_credit_notes = fields.Boolean(
        related="team_id.helpdesk_use_credit_notes",
        export_string_translation=False,
    )
    use_coupons = fields.Boolean(
        related="team_id.helpdesk_use_coupons",
        string="Use Coupons",
    )
    use_giftcards = fields.Boolean(
        related="team_id.helpdesk_use_giftcards",
        string="Use Gift Cards",
    )
    use_product_returns = fields.Boolean(
        related="team_id.helpdesk_use_product_returns",
        export_string_translation=False,
    )
    use_product_replacements = fields.Boolean(
        related="team_id.helpdesk_use_product_replacements",
        export_string_translation=False,
    )
    use_product_repairs = fields.Boolean(
        related="team_id.helpdesk_use_product_repairs",
        export_string_translation=False,
    )
    use_rating = fields.Boolean(
        related="team_id.helpdesk_use_rating",
        export_string_translation=False,
    )

    is_partner_email_update = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_partner_email_update",
    )
    is_partner_phone_update = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_partner_phone_update",
    )
    website_message_ids = fields.One2many(
        export_string_translation=False,
        domain=lambda self: [
            ("model", "=", self._name),
            (
                "message_type",
                "in",
                ["email", "comment", "email_outgoing", "auto_comment"],
            ),
        ],
    )

    first_response_hours = fields.Float(
        string="Hours to First Response",
        copy=False,
        aggregator="avg",
    )
    avg_response_hours = fields.Float(
        string="Average Hours to Respond",
        copy=False,
        aggregator="avg",
    )
    oldest_unanswered_customer_message_date = fields.Datetime(
        export_string_translation=False
    )
    answered_customer_message_count = fields.Integer(
        string="# Exchanges",
        aggregator="avg",
    )
    total_response_hours = fields.Float(
        string="Total Exchange Time in Hours",
        copy=False,
        aggregator="avg",
    )
    display_extra_info = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_extra_info",
    )

    @api.depends("stage_id", "kanban_state")
    def _compute_kanban_state_label(self) -> None:
        for ticket in self:
            if ticket.kanban_state == "normal":
                ticket.kanban_state_label = ticket.legend_normal
            elif ticket.kanban_state == "blocked":
                ticket.kanban_state_label = ticket.legend_blocked
            else:
                ticket.kanban_state_label = ticket.legend_done

    @api.depends("team_id")
    def _compute_domain_user_ids(self) -> None:
        user_ids = self.env.ref("helpdesk.group_helpdesk_user").all_user_ids.ids
        for ticket in self:
            ticket_user_ids = []
            ticket_sudo = ticket.sudo()
            if (
                ticket_sudo.team_id
                and ticket_sudo.team_id.helpdesk_privacy_visibility
                == "invited_internal"
            ):
                ticket_user_ids = ticket_sudo.team_id.message_partner_ids.user_ids.ids
            ticket.domain_user_ids = [Command.set(user_ids + ticket_user_ids)]

    def _compute_access_url(self):
        super()._compute_access_url()
        for ticket in self:
            ticket.access_url = "/my/ticket/%s" % ticket.id

    @api.depends("sla_status_ids.deadline", "sla_status_ids.reached_datetime")
    def _compute_sla_reached_late(self) -> None:
        mapping = {}
        if self.ids:
            self.env.cr.execute(
                """
                SELECT ticket_id, COUNT(id) AS reached_late_count
                FROM helpdesk_sla_status
                WHERE ticket_id = ANY(%s) AND (deadline < reached_datetime OR (deadline < %s AND reached_datetime IS NULL))
                GROUP BY ticket_id
            """,
                (list(self.ids), fields.Datetime.now()),
            )
            mapping = dict(self.env.cr.fetchall())

        for ticket in self:
            ticket.sla_reached_late = mapping.get(ticket.id, 0) > 0

    @api.depends("sla_status_ids.deadline", "sla_status_ids.reached_datetime")
    def _compute_sla_reached(self) -> None:
        sla_status_read_group = self.env["helpdesk.sla.status"]._read_group(
            [("exceeded_hours", "<", 0), ("ticket_id", "in", self.ids)],
            ["ticket_id"],
        )
        sla_status_ids_per_ticket = {ticket.id for [ticket] in sla_status_read_group}
        for ticket in self:
            ticket.sla_reached = ticket.id in sla_status_ids_per_ticket

    @api.depends("sla_status_ids.deadline", "sla_status_ids.reached_datetime")
    def _compute_sla_deadline(self) -> None:
        now = fields.Datetime.now()
        for ticket in self:
            if not (ticket.team_id and ticket.team_id.helpdesk_use_sla):
                continue
            min_deadline = False
            for status in ticket.sla_status_ids:
                if status.reached_datetime or not status.deadline:
                    continue
                if not min_deadline or status.deadline < min_deadline:
                    min_deadline = status.deadline

            ticket.update(
                {
                    "sla_deadline": min_deadline,
                    "sla_deadline_hours": ticket.team_id.resource_calendar_id.get_work_duration_data(
                        now, min_deadline, compute_leaves=True
                    )["hours"]
                    if min_deadline
                    else 0.0,
                }
            )

    @api.depends("sla_deadline", "sla_reached_late")
    def _compute_sla_fail(self) -> None:
        now = fields.Datetime.now()
        for ticket in self:
            if ticket.sla_deadline:
                ticket.sla_fail = (ticket.sla_deadline < now) or ticket.sla_reached_late
            else:
                ticket.sla_fail = ticket.sla_reached_late

    @api.depends("partner_email", "partner_id")
    def _compute_is_partner_email_update(self) -> None:
        for ticket in self:
            ticket.is_partner_email_update = ticket._get_partner_email_update()

    @api.depends("phone_ids.sanitized", "partner_id.phone_ids.sanitized")
    def _compute_is_partner_phone_update(self) -> None:
        for ticket in self:
            ticket.is_partner_phone_update = ticket._get_partner_phone_update()

    @api.model
    def _search_sla_fail(self, operator, value):
        if operator != "in":
            return NotImplemented
        datetime_now = fields.Datetime.now()
        return [
            "|",
            ("sla_reached_late", "=", True),
            ("sla_deadline", "<", datetime_now),
        ]

    @api.depends("sla_deadline", "sla_reached", "sla_reached_late")
    def _compute_sla_success(self) -> None:
        now = fields.Datetime.now()
        for ticket in self:
            ticket.sla_success = (
                ticket.sla_reached
                and not ticket.sla_reached_late
                and (not ticket.sla_deadline or ticket.sla_deadline > now)
            )

    @api.model
    def _search_sla_success(self, operator, value):
        if operator != "in":
            return NotImplemented
        datetime_now = fields.Datetime.now()
        return [
            ("sla_reached", "=", True),
            ("sla_reached_late", "=", False),
            "|",
            ("sla_deadline", "=", False),
            ("sla_deadline", ">", datetime_now),
        ]

    @api.depends("team_id")
    def _compute_user_and_stage_ids(self) -> None:
        for ticket in self.filtered(lambda ticket: ticket.team_id):
            if not ticket.user_id:
                ticket.user_id = ticket.team_id._get_user_to_assign(
                    {ticket.team_id: 1}
                )[ticket.team_id.id][0]
            if (
                not ticket.stage_id
                or ticket.stage_id not in ticket.team_id.helpdesk_stage_ids
            ):
                ticket.stage_id = ticket.team_id._get_stage()[ticket.team_id.id]

    @api.depends("partner_id")
    def _compute_partner_name(self) -> None:
        self.fetch(["partner_id"])
        for ticket in self:
            if ticket.partner_id:
                ticket.partner_name = ticket.partner_id.name

    @api.depends("partner_id.email")
    def _compute_partner_email(self) -> None:
        self.fetch(["partner_id"])
        for ticket in self:
            if ticket.partner_id:
                ticket.partner_email = ticket.partner_id.email

    def _inverse_partner_email(self) -> None:
        for ticket in self:
            if ticket._get_partner_email_update():
                ticket.partner_id.email = ticket.partner_email

    @api.depends("partner_id.phone_ids")
    def _compute_phone_ids(self) -> None:
        self.fetch(["partner_id"])
        for ticket in self:
            if ticket.partner_id:
                ticket.phone_ids = ticket.partner_id.phone_ids

    def _inverse_phone_ids(self) -> None:
        for ticket in self:
            if (
                ticket._get_partner_phone_update() or not ticket.partner_id.phone_ids
            ) and ticket.phone_ids:
                ticket = ticket.sudo()
                ticket.partner_id.phone_ids = ticket.phone_ids

    @api.depends("partner_id", "partner_email", "phone_ids")
    def _compute_partner_ticket_count(self) -> None:
        for ticket in self:
            partner_tickets = (
                self.search_fetch(
                    [
                        (
                            "partner_id",
                            "child_of",
                            ticket.partner_id.commercial_partner_id.id,
                        )
                    ],
                    ["fold"],
                )
                if ticket.partner_id
                else ticket
            )
            ticket.partner_ticket_ids = partner_tickets
            partner_tickets -= ticket._origin
            ticket.partner_ticket_count = len(partner_tickets) if partner_tickets else 0
            open_ticket = partner_tickets.filtered(lambda ticket: not ticket.fold)
            ticket.partner_open_ticket_count = len(open_ticket)

    @api.depends("assign_date")
    def _compute_assign_hours(self) -> None:
        for ticket in self:
            create_date = fields.Datetime.from_string(ticket.create_date)
            if (
                create_date
                and ticket.assign_date
                and ticket.team_id.resource_calendar_id
            ):
                duration_data = (
                    ticket.team_id.resource_calendar_id.get_work_duration_data(
                        create_date,
                        fields.Datetime.from_string(ticket.assign_date),
                        compute_leaves=True,
                    )
                )
                ticket.assign_hours = duration_data["hours"]
            else:
                ticket.assign_hours = False

    @api.depends("create_date", "close_date")
    def _compute_close_hours(self) -> None:
        for ticket in self:
            create_date = fields.Datetime.from_string(ticket.create_date)
            if (
                create_date
                and ticket.close_date
                and ticket.team_id.resource_calendar_id
            ):
                duration_data = (
                    ticket.team_id.resource_calendar_id.get_work_duration_data(
                        create_date,
                        fields.Datetime.from_string(ticket.close_date),
                        compute_leaves=True,
                    )
                )
                ticket.close_hours = duration_data["hours"]
            else:
                ticket.close_hours = False

    @api.depends("close_hours")
    def _compute_open_hours(self) -> None:
        for ticket in self:
            if ticket.create_date:
                if ticket.close_date:
                    time_difference = ticket.close_date - fields.Datetime.from_string(
                        ticket.create_date
                    )
                else:
                    time_difference = (
                        fields.Datetime.now()
                        - fields.Datetime.from_string(ticket.create_date)
                    )
                ticket.open_hours = (
                    time_difference.seconds
                ) / 3600 + time_difference.days * 24
            else:
                ticket.open_hours = 0

    def _compute_display_extra_info(self) -> None:
        self.display_extra_info = self.env.user.has_group("base.group_multi_company")

    @api.model
    def _search_open_hours(self, operator, value):
        if operator == "in":
            return Domain.OR(self._search_open_hours("=", v) for v in value)
        if operator == "not in":
            return Domain.AND(self._search_open_hours("!=", v) for v in value)

        dt = fields.Datetime.now() - relativedelta(hours=value)
        domain_closed = Domain("close_hours", operator, value)
        if operator in ["<", "<=", ">", ">="]:
            domain_unclosed = ~Domain("create_date", operator, dt)
        elif operator in ["=", "!="]:
            dt = dt.replace(minute=0, second=0, microsecond=0)
            domain_unclosed = Domain("create_date", ">=", dt) & Domain(
                "create_date", "<", dt + relativedelta(hours=1)
            )
            if operator == "!=":
                domain_unclosed = ~domain_unclosed
        else:
            return NotImplemented
        return (Domain("close_date", "=", False) & domain_unclosed) | (
            Domain("close_date", "!=", False) & domain_closed
        )

    def _get_rotting_depends_fields(self):
        return super()._get_rotting_depends_fields() + ["close_date", "kanban_state"]

    def _get_domain_rotting_records(self):
        return super()._get_domain_rotting_records() & Domain("close_date", "=", False)

    def _get_partner_email_update(self):
        self.check_singleton()
        if (
            self.partner_id.email
            and self.partner_email
            and self.partner_email != self.partner_id.email
        ):
            ticket_email_normalized = (
                tools.email_normalize(self.partner_email) or self.partner_email or False
            )
            partner_email_normalized = (
                tools.email_normalize(self.partner_id.email)
                or self.partner_id.email
                or False
            )
            return ticket_email_normalized != partner_email_normalized
        return False

    def _get_partner_phone_update(self) -> bool:
        self.check_singleton()
        if self.partner_id.phone_ids and self.phone_ids:
            return set(self.phone_ids.mapped("sanitized")) != set(
                self.partner_id.phone_ids.mapped("sanitized")
            )
        return False

    def action_customer_preview(self) -> dict:
        self.check_singleton()
        if self.team_privacy_visibility != "portal" or not self.partner_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "danger",
                    "message": self.env._(
                        "At this time, there is no preview available to show. The current ticket cannot be accessed by the customer, as it belongs to a helpdesk team that is not publicly available, or there is no customer associated with the ticket."
                    ),
                },
            }
        return {
            "type": "ir.actions.act_url",
            "url": self.get_portal_url(),
            "target": "self",
        }

    @api.depends("ticket_ref", "partner_name")
    @api.depends_context("with_partner")
    def _compute_display_name(self):
        display_partner_name = self.env.context.get("with_partner", False)
        ticket_with_name = self.filtered("name")
        for ticket in ticket_with_name:
            name = ticket.name
            if ticket.ticket_ref:
                name += f" (#{ticket.ticket_ref})"
            if display_partner_name and ticket.partner_name:
                name += f" - {ticket.partner_name}"
            ticket.display_name = name
        return super(HelpdeskTicket, self - ticket_with_name)._compute_display_name()

    @api.model
    def get_empty_list_help(self, help_message):
        self = self.with_context(
            empty_list_help_id=self.env.context.get("default_team_id"),
            empty_list_help_model="team.team",
            empty_list_help_document_name=self.env._("tickets"),
        )
        return super().get_empty_list_help(help_message)

    def create_action(self, action_ref, title, search_view_ref):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(action_ref)
        action = clean_action(action, self.env)
        if title:
            action["display_name"] = title
        if search_view_ref:
            action["search_view_id"] = self.env.ref(search_view_ref).read()[0]
        if "views" not in action:
            action["views"] = [(False, view) for view in action["view_mode"].split(",")]
        return action

    @api.model
    def _update_vals_by_tags(self, vals_list) -> None:
        if not vals_list:
            return
        domain = Domain.OR(
            [("team_id", "=", team_id), ("tag_id", "in", tag_ids)]
            for team_id, tag_ids, _dummy in vals_list
        )
        tag_assignment_res = (
            self.env["helpdesk.tag.assignment"]
            .sudo()
            ._read_group(
                domain,
                ["team_id", "tag_id", "user_ids"],
            )
        )
        users_per_team_and_tag = defaultdict(set)
        all_possible_users_ids = set()
        for team, tag, user in tag_assignment_res:
            users_per_team_and_tag[(team.id, tag.id)].add(user.id)
            all_possible_users_ids.add(user.id)
        all_possible_users = self.env["res.users"].browse(all_possible_users_ids)
        all_team_ids = {vals[0] for vals in vals_list}
        users_per_working_days = (
            all_possible_users._get_working_users_per_first_working_day()
        )

        tickets_per_user_per_team = defaultdict(dict)
        for team, _dummy, user in tag_assignment_res:
            tickets_per_user_per_team[team.id][user.id] = 0
        ticket_count_data = self.env["helpdesk.ticket"]._read_group(
            [
                ("stage_id.fold", "=", False),
                ("user_id", "in", all_possible_users.ids),
                ("team_id", "in", list(all_team_ids)),
            ],
            ["user_id", "team_id"],
            ["__count"],
        )
        for user, team, open_tickets in ticket_count_data:
            tickets_per_user_per_team[team.id][user.id] = open_tickets

        for team_id, tag_ids, vals in vals_list:
            possible_user_ids = {
                user_id
                for tag_id in tag_ids
                for user_id in users_per_team_and_tag.get((team_id, tag_id), [])
            }
            if possible_user_ids:
                for user_ids in users_per_working_days:
                    if available_user_ids := set(user_ids) & possible_user_ids:
                        count_per_user = filter(
                            lambda item: item[0] in available_user_ids,
                            tickets_per_user_per_team[team_id].items(),
                        )
                        chosen_user_id = min(
                            count_per_user, key=lambda count: count[1]
                        )[0]
                        vals["user_id"] = chosen_user_id
                        tickets_per_user_per_team[team_id][chosen_user_id] += 1
                        break

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()

        team_ids = {vals["team_id"] for vals in vals_list if vals.get("team_id")}
        tickets_to_assign_by_tags = []
        teams = self.env["team.team"].browse(team_ids)

        default_stage_per_team_id = teams._get_stage()

        team_per_team_id = dict(zip(team_ids, teams, strict=False))
        ticket_amount_per_team = defaultdict(int)
        for vals in vals_list:
            if not (team_id := vals.get("team_id")):
                continue
            stage = (
                self.env["helpdesk.stage"].browse(vals["stage_id"])
                if "stage_id" in vals
                else default_stage_per_team_id[team_id]
            )
            team = team_per_team_id[team_id]
            if stage.fold or vals.get("user_id") or not team.helpdesk_auto_assignment:
                continue
            if team.helpdesk_assign_method == "tags":
                if tag_ids := vals.get("tag_ids"):
                    tag_ids = self._fields["tag_ids"].convert_to_cache(tag_ids, self)
                    tickets_to_assign_by_tags.append((team.id, tag_ids, vals))
            else:
                ticket_amount_per_team[team] += 1

        self._update_vals_by_tags(tickets_to_assign_by_tags)
        assignees_per_team_id = self.env["team.team"]._get_user_to_assign(
            ticket_amount_per_team
        )

        for vals in vals_list:
            partner_id = vals.get("partner_id", False)
            partner_name = vals.get("partner_name", False)
            partner_email = vals.get("partner_email", False)
            if partner_email and not partner_id:
                company_id = (
                    self.env["team.team"].browse(vals["team_id"]).company_id.id
                    if vals.get("team_id")
                    else False
                )
                suggested_name = (
                    tools.parse_contact_from_email(partner_name)[0]
                    or tools.parse_contact_from_email(partner_email)[0]
                )
                vals["partner_id"] = self._get_or_create_customer_partner(
                    partner_email, suggested_name, company_id
                ).id

        partners = self.env["res.partner"].browse(
            [
                vals["partner_id"]
                for vals in vals_list
                if "partner_id" in vals
                and vals.get("partner_id")
                and "partner_email" not in vals
            ]
        )
        partner_email_map = {partner.id: partner.email for partner in partners}
        partner_name_map = {partner.id: partner.name for partner in partners}
        company_per_team_id = {t.id: t.company_id for t in teams}
        for vals in vals_list:
            company = company_per_team_id.get(vals.get("team_id", False))
            vals["ticket_ref"] = (
                self.env["ir.sequence"]
                .with_company(company)
                .sudo()
                .next_by_code("helpdesk.ticket")
            )
            if team_id := vals.get("team_id"):
                if "stage_id" not in vals:
                    vals["stage_id"] = default_stage_per_team_id[team_id].id
                if self.env["helpdesk.stage"].browse(vals["stage_id"]).fold:
                    vals["close_date"] = now
                if "user_id" not in vals and team_id in assignees_per_team_id:
                    vals["user_id"] = assignees_per_team_id[team_id].pop()
                if vals.get("user_id"):
                    vals["assign_date"] = fields.Datetime.now()
                    vals["assign_hours"] = 0

            if vals.get("partner_id") in partner_email_map:
                vals["partner_email"] = partner_email_map.get(vals["partner_id"])
            if vals.get("partner_id") in partner_name_map:
                vals["partner_name"] = partner_name_map.get(vals["partner_id"])

            if vals.get("stage_id"):
                vals["date_last_stage_update"] = now
            vals["oldest_unanswered_customer_message_date"] = now

        tickets = super().create(vals_list)

        all_partner_emails = []
        for ticket in tickets:
            all_partner_emails += tools.email_normalize_all(ticket.email_cc)
        partners = self.env["res.partner"].search([("email", "in", all_partner_emails)])
        partner_per_email = {
            partner.email: partner
            for partner in partners
            if not all(u.share for u in partner.user_ids)
        }

        for ticket in tickets:
            partner_ids = []
            if ticket.partner_id:
                partner_ids = ticket.partner_id.ids
            if ticket.email_cc:
                partners_with_internal_user = self.env["res.partner"]
                for email in tools.email_normalize_all(ticket.email_cc):
                    new_partner = partner_per_email.get(email)
                    if new_partner:
                        partners_with_internal_user |= new_partner
                if partners_with_internal_user:
                    ticket._send_email_notify_to_cc(partners_with_internal_user)
                    partner_ids += partners_with_internal_user.ids
            if partner_ids:
                ticket.message_subscribe(partner_ids)

            ticket._portal_get_or_create_token()

        tickets.sudo()._sla_apply()

        return tickets

    @api.model
    def _get_or_create_customer_partner(self, email, name, company_id):
        return self.env["mixin.mail.thread"]._partner_get_or_create_from_emails_single(
            [email],
            additional_values={
                tools.mail.email_normalize(email) or email: {
                    "name": name,
                    "company_id": company_id,
                }
            },
            filter_found=lambda partner: (
                not partner.company_id or partner.company_id.id == company_id
            ),
        )

    def write(self, vals):
        assigned_tickets = closed_tickets = self.browse()
        if vals.get("user_id"):
            assigned_tickets = self.filtered(lambda ticket: not ticket.assign_date)

        if vals.get("stage_id"):
            if self.env["helpdesk.stage"].browse(vals.get("stage_id")).fold:
                closed_tickets = self.filtered(lambda ticket: not ticket.close_date)
            else:
                vals["closed_by_partner"] = False
                vals["close_date"] = False

        now = fields.Datetime.now()

        if "stage_id" in vals:
            vals["date_last_stage_update"] = now
            if "kanban_state" not in vals:
                vals["kanban_state"] = "normal"

        if "kanban_state" in vals:
            vals["date_last_stage_update"] = now

        old_tag_ids_per_ticket_id = {}
        if "tag_ids" in vals:
            old_tag_ids_per_ticket_id = {t.id: set(t.tag_ids.ids) for t in self}

        res = super(HelpdeskTicket, self - assigned_tickets - closed_tickets).write(
            vals
        )
        res &= super(HelpdeskTicket, assigned_tickets - closed_tickets).write(
            dict(vals, assign_date=now)
        )
        res &= super(HelpdeskTicket, closed_tickets - assigned_tickets).write(
            dict(vals, close_date=now, oldest_unanswered_customer_message_date=False)
        )
        res &= super(HelpdeskTicket, assigned_tickets & closed_tickets).write(
            dict(vals, assign_date=now, close_date=now)
        )

        if vals.get("partner_id"):
            self.message_subscribe([vals["partner_id"]])

        sla_triggers = self._sla_reset_trigger()
        if any(field_name in sla_triggers for field_name in vals):
            self.sudo()._sla_apply(keep_reached=True)
        if "stage_id" in vals:
            self.sudo()._sla_reach(vals["stage_id"])

        if (
            "stage_id" in vals
            and self.env["helpdesk.stage"].browse(vals["stage_id"]).fold
        ):
            odoobot_partner_id = self.env["ir.model.data"]._xmlid_to_res_id(
                "base.partner_root"
            )
            for ticket in self:
                exceeded_hours = ticket.sla_status_ids.mapped("exceeded_hours")
                if exceeded_hours:
                    min_hours = min(
                        [hours for hours in exceeded_hours if hours > 0],
                        default=min(exceeded_hours),
                    )
                    message = (
                        self.env._(
                            "This ticket was successfully closed %s hours before its SLA deadline.",
                            round(abs(min_hours)),
                        )
                        if min_hours < 0
                        else self.env._(
                            "This ticket was closed %s hours after its SLA deadline.",
                            round(min_hours),
                        )
                    )
                    ticket.message_post(
                        body=message,
                        subtype_xmlid="mail.mt_note",
                        author_id=odoobot_partner_id,
                    )
        elif old_tag_ids_per_ticket_id:
            unassigned_tickets_to_assign = self.filtered(
                lambda t: (
                    not t.user_id
                    and t.team_id.helpdesk_auto_assignment
                    and t.team_id.helpdesk_assign_method == "tags"
                    and not t.stage_id.fold
                )
            )
            if unassigned_tickets_to_assign:
                vals_list = [
                    (ticket.team_id.id, list(added_tags), {})
                    for ticket in unassigned_tickets_to_assign
                    if (
                        added_tags := set(ticket.tag_ids.ids)
                        - old_tag_ids_per_ticket_id[ticket.id]
                    )
                ]
                if vals_list:
                    self._update_vals_by_tags(vals_list)
                    for ticket, vals_dict in zip(
                        unassigned_tickets_to_assign,
                        list(zip(*vals_list, strict=False))[2],
                        strict=False,
                    ):
                        if vals_dict:
                            ticket.write(vals_dict)
        return res

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        has_default_user = default and "user_id" in default
        active_users = self.env["res.users"]
        if not has_default_user:
            active_users = self.user_id.filtered("active")
        for ticket, vals in zip(self, vals_list, strict=False):
            vals["name"] = self.env._("%s (copy)", ticket.name)
            if (
                not has_default_user
                and ticket.user_id
                and ticket.user_id not in active_users
            ):
                vals["user_id"] = False
        return vals_list

    def _unsubscribe_portal_users(self) -> None:
        self.message_unsubscribe(
            partner_ids=self.message_partner_ids.filtered("user_ids.share").ids
        )

    def website_form_input_filter(self, request, values):
        if "partner_id" in values:
            values.pop("partner_name", None)
            values.pop("partner_email", None)
        return values

    @api.model
    def _sla_reset_trigger(self):
        return ["team_id", "priority", "tag_ids", "partner_id"]

    def _sla_apply(self, keep_reached=False):
        sla_per_tickets = self._sla_find()

        sla_status_value_list = []
        for tickets, slas in sla_per_tickets.items():
            sla_status_value_list += tickets._sla_generate_status_values(
                slas, keep_reached=keep_reached
            )

        sla_status_to_remove = self.mapped("sla_status_ids")
        if keep_reached:
            sla_status_to_remove = sla_status_to_remove.filtered(
                lambda status: not status.reached_datetime
            )

        sla_status_to_remove.unlink()
        return self.env["helpdesk.sla.status"].create(sla_status_value_list)

    def _sla_find_domain(self) -> list:
        return [
            ("team_id", "=", self.team_id.id),
            ("priority", "=", self.priority),
            ("stage_id.sequence", ">=", self.stage_id.sequence),
        ]

    @api.model
    def _sla_find_false_domain(self):
        return [("partner_ids", "=", False)]

    def _sla_find_extra_domain(self):
        self.check_singleton()
        return [
            "|",
            ("partner_ids", "parent_of", self.partner_id.ids),
            ("partner_ids", "child_of", self.partner_id.ids),
        ]

    def _sla_find(self):
        tickets_map = {}
        sla_domain_map = {}

        def _generate_key(ticket):
            fields_list = self._sla_reset_trigger()
            key = []
            for field_name in fields_list:
                if ticket._fields[field_name].type == "many2one":
                    key.append(ticket[field_name].id)
                else:
                    key.append(ticket[field_name])
            return tuple(key)

        for ticket in self:
            if ticket.team_id.helpdesk_use_sla:
                key = _generate_key(ticket)
                tickets_map.setdefault(key, self.env["helpdesk.ticket"])
                tickets_map[key] |= ticket
                if key not in sla_domain_map:
                    sla_domain_map[key] = Domain.AND(
                        [
                            ticket._sla_find_domain(),
                            Domain.OR(
                                [
                                    ticket._sla_find_extra_domain(),
                                    self._sla_find_false_domain(),
                                ]
                            ),
                        ]
                    )

        result = {}
        for key, tickets in tickets_map.items():
            domain = sla_domain_map[key]
            slas = self.env["helpdesk.sla"].search(domain)
            result[tickets] = slas.filtered_domain(
                ["|", ("tag_ids", "=", False), ("tag_ids", "in", tickets.tag_ids.ids)]
            )
        return result

    def _sla_generate_status_values(self, slas, keep_reached=False):
        exclude_slas_per_ticket = {}
        if keep_reached:
            exclude_slas_per_ticket = dict(
                self.env["helpdesk.sla.status"]._read_group(
                    domain=[
                        ("reached_datetime", "!=", False),
                        ("ticket_id", "in", self.ids),
                    ],
                    groupby=["ticket_id"],
                    aggregates=["sla_id:recordset"],
                )
            )
        result = []
        for ticket in self:
            exclude_slas = exclude_slas_per_ticket.get(ticket, self.env["helpdesk.sla"])
            result.extend(
                {
                    "ticket_id": ticket.id,
                    "sla_id": sla.id,
                    "reached_datetime": fields.Datetime.now()
                    if ticket.stage_id == sla.stage_id
                    else False,
                }
                for sla in slas - exclude_slas
            )
        return result

    def _sla_reach(self, stage_id) -> None:
        stage = self.env["helpdesk.stage"].browse(stage_id)
        stages = self.env["helpdesk.stage"].search(
            [
                ("sequence", "<=", stage.sequence),
                ("team_ids", "in", self.mapped("team_id").ids),
            ]
        )
        sla_status = self.env["helpdesk.sla.status"].search(
            [("ticket_id", "in", self.ids)]
        )
        sla_not_reached = sla_status.filtered(
            lambda sla: not sla.reached_datetime and sla.sla_stage_id in stages
        )
        sla_not_reached.write({"reached_datetime": fields.Datetime.now()})
        (sla_status - sla_not_reached).filtered(
            lambda x: x.sla_stage_id not in stages
        ).write({"reached_datetime": False})

    def action_view_helpdesk_ticket(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "helpdesk.helpdesk_ticket_action_main_tree"
        )
        action.update(
            {
                "domain": [
                    ("id", "!=", self.id),
                    ("id", "in", self.partner_ticket_ids.ids),
                ],
                "context": {
                    **self.env["ir.actions.actions"]._eval_action_context(
                        action.get("context", {})
                    ),
                    "create": False,
                },
            }
        )
        return action

    def action_view_ratings(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "helpdesk.rating_rating_action_helpdesk"
        )
        if self.rating_count == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": self.rating_ids[0].id,
                    "views": [
                        (view_id, view_type)
                        for view_id, view_type in action["views"]
                        if view_type == "form"
                    ],
                }
            )
        return action

    def _mail_get_governing_alias(self):
        self.check_singleton()
        return self.team_id.helpdesk_alias_id.alias_id

    def _mail_get_customer_information(self):
        email_keys_to_values = super()._mail_get_customer_information()

        for ticket in self:
            email_key = (
                tools.email_normalize(ticket.partner_email) or ticket.partner_email
            )
            if not email_key and len(self) > 1:
                continue
            email_keys_to_values.setdefault(email_key, {}).update(
                {
                    "company_id": ticket.company_id.id,
                    "name": ticket.partner_name
                    or tools.parse_contact_from_email(ticket.partner_email)[0]
                    or ticket.partner_email,
                    "phone": ticket._phone_get_number().number,
                }
            )
        return email_keys_to_values

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        values = dict(
            custom_values or {},
            partner_email=msg_dict.get("from"),
            partner_name=msg_dict.get("from"),
            partner_id=msg_dict.get("author_id"),
        )
        partner = self.env["res.partner"].browse(values.get("partner_id"))
        team = self.env["team.team"].browse(values.get("team_id"))
        if team and partner.company_id and partner.company_id != team.company_id:
            values.pop("partner_id")
        ticket = super(
            HelpdeskTicket, self.with_context(mail_notify_author=True)
        ).message_new(msg_dict, custom_values=values)
        partner_ids = ticket._partner_get_or_create_from_emails_single(
            tools.email_split(
                (msg_dict.get("to") or "") + "," + (msg_dict.get("cc") or "")
            )
        ).ids
        customer_ids = ticket._partner_get_or_create_from_emails_single(
            tools.email_split(values["partner_email"])
        ).ids
        partner_ids += customer_ids
        if customer_ids and not values.get("partner_id"):
            ticket.partner_id = customer_ids[0]
        if partner_ids:
            ticket.message_subscribe(partner_ids)
        return ticket

    def message_update(self, msg_dict, update_vals=None):
        for ticket in self:
            if partners := ticket._partner_get_or_create_from_emails_single(
                tools.email_split(
                    (msg_dict.get("to") or "") + "," + (msg_dict.get("cc") or "")
                ),
                no_create=True,
            ):
                self.message_subscribe(partners.ids)
        return super().message_update(msg_dict, update_vals=update_vals)

    def _message_compute_subject(self):
        self.check_singleton()
        return self.name

    def _message_post_after_hook(self, message, msg_vals):
        if not self.partner_email:
            return super()._message_post_after_hook(message, msg_vals)

        if self.partner_id and not self.partner_id.email:
            self.partner_id.email = self.partner_email

        if not self.partner_id:
            email_normalized = tools.email_normalize(self.partner_email)
            new_partner = message.partner_ids.filtered(
                lambda partner: (
                    partner.email == self.partner_email
                    or (
                        email_normalized
                        and partner.email_normalized == email_normalized
                    )
                )
            )
            if new_partner:
                if new_partner[0].email_normalized:
                    email_domain = (
                        "partner_email",
                        "in",
                        [new_partner[0].email, new_partner[0].email_normalized],
                    )
                else:
                    email_domain = ("partner_email", "=", new_partner[0].email)
                self.search(
                    [
                        ("partner_id", "=", False),
                        email_domain,
                    ]
                ).write({"partner_id": new_partner[0].id})
        if (
            not self.description
            and message.subtype_id == self._creation_subtype()
            and msg_vals.get("message_type") == "email"
            and tools.email_normalize(self.partner_email)
            == tools.email_normalize(message.email_from)
            and msg_vals.get("body")
        ):
            source_html = msg_vals.get("body")
            doc = html.fromstring(source_html)

            signature_xpath = (
                '//*[@id="Signature"] | '
                '//*[@data-smartmail="gmail_signature"] | '
                '//span[normalize-space(.) = "--"]'
            )

            for element in doc.xpath(signature_xpath):
                element.getparent().remove(element)

            cleaned_html = html.tostring(doc, encoding="unicode").strip()
            self.description = html_sanitize(cleaned_html)

        return super()._message_post_after_hook(message, msg_vals)

    def _send_email_notify_to_cc(self, partners_to_notify) -> None:
        self.check_singleton()
        template_id = self.env["ir.model.data"]._xmlid_to_res_id(
            "helpdesk.ticket_invitation_follower", raise_if_not_found=False
        )
        if not template_id:
            return
        ticket_model_description = self.env["ir.model"]._get(self._name).display_name
        values = {
            "object": self,
        }
        for partner in partners_to_notify:
            values["partner_name"] = partner.name
            assignation_msg = self.env["ir.qweb"]._render(
                "helpdesk.ticket_invitation_follower", values, minimal_qcontext=True
            )
            self.message_notify(
                subject=self.env._(
                    "You have been invited to follow %s", self.display_name
                ),
                body=assignation_msg,
                partner_ids=partner.ids,
                email_layout_xmlid="mail.mail_notification_layout",
                model_description=ticket_model_description,
                mail_auto_delete=True,
            )

    def _track_template(self, changes):
        res = super()._track_template(changes)
        ticket = self[0]
        if (
            "stage_id" in changes
            and ticket.stage_id.template_id
            and ticket.partner_email
        ):
            res["stage_id"] = (
                ticket.stage_id.template_id,
                {
                    "auto_delete_keep_log": False,
                    "subtype_id": self.env["ir.model.data"]._xmlid_to_res_id(
                        "mail.mt_note"
                    ),
                    "email_layout_xmlid": "mail.mail_notification_light",
                },
            )
        return res

    def _creation_subtype(self):
        return self.env.ref("helpdesk.mt_ticket_new")

    def _track_subtype(self, init_values):
        self.check_singleton()
        if "stage_id" in init_values:
            return self.env.ref("helpdesk.mt_ticket_stage")
        return super()._track_subtype(init_values)

    def _notify_get_reply_to_addresses(self):
        addresses = self.team_id.sudo()._notify_get_usage_reply_to_addresses("helpdesk")
        res = {
            ticket.id: addresses[ticket.team_id.id]
            for ticket in self
            if ticket.team_id and ticket.team_id.id in addresses
        }
        leftover = self.filtered(lambda rec: not rec.team_id)
        if leftover:
            res.update(super(HelpdeskTicket, leftover)._notify_get_reply_to_addresses())
        return res

    def _rating_apply_get_default_subtype_id(self):
        return self.env["ir.model.data"]._xmlid_to_res_id("helpdesk.mt_ticket_rated")

    def _rating_get_parent_field_name(self):
        return "team_id"

    def _mail_get_message_subtypes(self):
        res = super()._mail_get_message_subtypes()
        if len(self) == 1 and self.team_id:
            team = self.team_id
            optional_subtypes = [
                (
                    "helpdesk_use_credit_notes",
                    self.env.ref("helpdesk.mt_ticket_refund_status"),
                ),
                (
                    "helpdesk_use_product_returns",
                    self.env.ref("helpdesk.mt_ticket_return_status"),
                ),
                (
                    "helpdesk_use_product_replacements",
                    self.env.ref("helpdesk.mt_ticket_delivery_status"),
                ),
                (
                    "helpdesk_use_product_repairs",
                    self.env.ref("helpdesk.mt_ticket_repair_status"),
                ),
            ]
            for field, subtype in optional_subtypes:
                if not team[field] and subtype in res:
                    res -= subtype
        return res

    @api.constrains("team_id")
    def _check_team_id_is_helpdesk_team(self) -> None:
        if teams := self.team_id.sudo().filtered(lambda team: not team.use_helpdesk):
            raise ValidationError(
                self.env._(
                    "%(teams)s is not a helpdesk team.",
                    teams=", ".join(teams.mapped("display_name")),
                )
            )

    @api.constrains("company_id", "partner_id")
    def _check_partner_id_has_the_same_company(self) -> None:
        for ticket in self:
            if (
                ticket.partner_id.company_id
                and ticket.partner_id.company_id != ticket.company_id
            ):
                raise UserError(
                    self.env._(
                        "The customer cannot belong to a different company than the ticket."
                    )
                )

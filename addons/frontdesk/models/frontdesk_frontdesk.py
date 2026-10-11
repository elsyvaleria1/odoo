import uuid
from datetime import datetime, timedelta

from odoo import Command, api, fields, models, tools
from odoo.libs.web import urljoin as url_join
from odoo.tools import frozendict

ASK_FIELDS_SELECTION = [
    ("required", "Required"),
    ("optional", "Optional"),
    ("none", "None"),
]

PLANNED_VISITOR_TIME = 45
MOBILE_CODE_SCOPE = tools.register_signed_scope(
    "kiosk-mobile",
    purpose="the code a visitor's phone presents to check in at a frontdesk",
    lifetime="dated: the day it is signed for, and one hour of use",
)


class FrontdeskFrontdesk(models.Model):
    _name = "frontdesk.frontdesk"
    _description = "Frontdesk"
    _inherit = ["mixin.user.favorite"]
    _order = "is_featured desc, is_user_favorite desc"
    _access_anchors = frozendict(
        {
            "owner": "responsible_ids",
        }
    )

    name = fields.Char(
        string="Frontdesk Name",
        required=True,
    )
    responsible_ids = fields.Many2many(
        comodel_name="res.users",
        string="Responsibles",
        required=True,
        help="Responsibles are people who will welcome the client and handle their drinks, etc.",
    )
    host_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Hosts",
        domain="[('company_id', '=', company_id), '|', ('work_email', '!=', False), ('phone_ids', '!=', False)]",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    theme = fields.Selection(
        selection=[("light", "Light"), ("dark", "Dark")],
        default="light",
    )
    image = fields.Image()
    host_selection = fields.Boolean(
        groups="frontdesk.frontdesk_group_user",
        help="Restrict the hosts available from the client to choose from.",
    )
    authenticate_guest = fields.Boolean(
        default=True,
        groups="frontdesk.frontdesk_group_user",
    )
    ask_phone = fields.Selection(
        selection=ASK_FIELDS_SELECTION,
        string="Phone",
        default="required",
        required=True,
    )
    ask_company = fields.Selection(
        selection=ASK_FIELDS_SELECTION,
        string="Organization",
        default="optional",
        required=True,
    )
    ask_email = fields.Selection(
        selection=ASK_FIELDS_SELECTION,
        string="Email",
        default="none",
        required=True,
    )
    notify_email = fields.Boolean(
        string="Notify by email",
        groups="frontdesk.frontdesk_group_user",
    )
    notify_sms = fields.Boolean(
        string="Notify by SMS",
        groups="frontdesk.frontdesk_group_user",
    )
    sms_template_id = fields.Many2one(
        comodel_name="sms.template",
        string="SMS Template",
        default=lambda self: self.env.ref(
            "frontdesk.frontdesk_sms_template", raise_if_not_found=False
        ),
        domain="[('model', '=', 'frontdesk.frontdesk')]",
    )
    self_check_in = fields.Boolean(
        string="Self Check-In",
        groups="frontdesk.frontdesk_group_user",
        help="Shows a QR code in the interface, for guests to check in from their mobile phone.",
    )
    drink_offer = fields.Boolean(
        string="Offer Drinks",
        groups="frontdesk.frontdesk_group_user",
    )
    drink_ids = fields.Many2many(comodel_name="frontdesk.drink")
    notify_discuss = fields.Boolean(
        string="Notify by discuss",
        default=True,
        groups="frontdesk.frontdesk_group_user",
    )
    description = fields.Html(groups="frontdesk.frontdesk_group_user")
    visitor_ids = fields.One2many(
        comodel_name="frontdesk.visitor",
        inverse_name="station_id",
        string="Visitors",
    )
    guest_on_site = fields.Integer(
        string="Guests On Site",
        compute="_compute_dashboard_data",
    )
    pending = fields.Integer(compute="_compute_dashboard_data")
    drink_to_serve = fields.Integer(
        string="Drinks to Serve",
        compute="_compute_dashboard_data",
    )
    latest_check_in = fields.Char(compute="_compute_dashboard_data")
    visitor_properties_definition = fields.PropertiesDefinition(
        string="Visitor Properties"
    )
    access_token = fields.Char(
        string="Security Token",
        default=lambda self: str(uuid.uuid4()),
        copy=False,
        readonly=True,
        required=True,
    )
    kiosk_url = fields.Char(
        string="Kiosk URL",
        compute="_compute_kiosk_url",
        groups="frontdesk.frontdesk_group_user",
    )
    favorite_user_ids = fields.Many2many(
        relation="frontdesk_favorite_user_rel",
        column1="frontdesk_id",
        column2="user_id",
    )
    active = fields.Boolean(default=True)
    is_featured = fields.Boolean(
        string="Featured",
        help="Featured stations are listed first, for every user.",
    )
    notify_warning = fields.Char(compute="_compute_notify_warning")

    @api.depends("host_ids.user_id", "host_ids.work_email", "host_ids.phone_ids")
    def _compute_notify_warning(self) -> None:
        for frontdesk in self:
            fallback_hosts = frontdesk.host_ids.filtered(
                lambda host: (
                    not host.user_id and bool(host.work_email or host.phone_ids)
                )
            )
            frontdesk.notify_warning = ", ".join(fallback_hosts.mapped("name"))

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.company_id and self.company_id != self.env.company:
            public_user = self.env.ref("base.public_user")
            if self.company_id not in public_user.company_ids:
                public_user.company_ids = [Command.link(self.company_id.id)]

    def _compute_dashboard_data(self) -> None:
        visitor_data = self.env["frontdesk.visitor"]._read_group(
            [
                ("state", "in", ("checked_in", "planned")),
                ("station_id", "in", self.ids),
            ],
            ["station_id", "state"],
            ["__count"],
        )
        checked_in_mapped = {
            station.id: count
            for station, state, count in visitor_data
            if state == "checked_in"
        }
        planned_mapped = {
            station.id: count
            for station, state, count in visitor_data
            if state == "planned"
        }
        drinks_data = self.env["frontdesk.visitor"]._read_group(
            [
                ("drink_ids", "!=", False),
                ("served", "=", False),
                ("state", "!=", "canceled"),
                ("station_id", "in", self.ids),
            ],
            ["station_id"],
            ["__count"],
        )
        drinks_data_mapped = {station.id: count for station, count in drinks_data}
        for frontdesk in self:
            guest_on_site = pending = drink_to_serve = 0
            latest_check_in = False
            if frontdesk.visitor_ids:
                guest_on_site = checked_in_mapped.get(frontdesk.id, 0)
                pending = planned_mapped.get(frontdesk.id, 0)
                drink_to_serve = drinks_data_mapped.get(frontdesk.id, 0)
                last_visitors = frontdesk.visitor_ids.filtered(
                    lambda v: v.state == "checked_in"
                )
                latest_check_in_time = last_visitors and last_visitors[-1].check_in
                if latest_check_in_time:
                    total_seconds = (
                        datetime.now() - latest_check_in_time
                    ).total_seconds()
                    time_diff = (
                        int(total_seconds / 60)
                        if total_seconds < 3600
                        else int(total_seconds / 3600)
                    )
                    latest_check_in = (
                        self.env._("Last Check-In: %s minutes ago", time_diff)
                        if total_seconds < 3600
                        else self.env._("Last Check-In: %s hours ago", time_diff)
                    )
            frontdesk.update(
                {
                    "guest_on_site": guest_on_site,
                    "pending": pending,
                    "drink_to_serve": drink_to_serve,
                    "latest_check_in": latest_check_in,
                }
            )

    @api.depends("access_token")
    def _compute_kiosk_url(self) -> None:
        for frontdesk in self:
            frontdesk.kiosk_url = url_join(
                self.env["frontdesk.frontdesk"].get_base_url(),
                "/kiosk/%s/%s" % (frontdesk.id, frontdesk.access_token),
            )

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        if default and "name" in default:
            return vals_list
        return [
            dict(vals, name=self.env._("%s (copy)", front_desk.name))
            for front_desk, vals in zip(self, vals_list, strict=False)
        ]

    def action_view_kiosk(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_url",
            "url": self.kiosk_url,
            "target": "self",
        }

    def install_kiosk(self) -> dict:
        return {
            "type": "ir.actions.act_url",
            "url": f"/scoped_app?app_id=frontdesk&path=kiosk/{self.id}/{self.access_token}",
            "target": "new",
        }

    def action_view_visitors(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Visitors"),
            "res_model": "frontdesk.visitor",
            "view_mode": "list,form,kanban,graph,pivot,calendar,gantt",
            "context": {
                "search_default_state_is_planned": 1,
                "search_default_state_is_checked_in": 1,
                "search_default_today": 1,
            },
            "domain": [("station_id.id", "=", self.id)],
        }

    def get_kiosk_url(self):
        return self.kiosk_url

    def _get_frontdesk_field(self) -> list:
        return [
            "description",
            "host_selection",
            "drink_offer",
            "self_check_in",
            "theme",
            "drink_ids",
            "ask_email",
            "ask_phone",
            "ask_company",
            "authenticate_guest",
        ]

    def _get_frontdesk_data(self):
        self.check_singleton()
        data = {
            "company": {"name": self.company_id.name, "id": self.company_id.id},
            "langs": [
                {"code": lang[0], "name": lang[1]}
                for lang in self.env["res.lang"].get_installed()
            ],
            "station": self.search_read(
                [("id", "=", self.id)], self._get_frontdesk_field()
            ),
        }
        if self.drink_offer:
            data["drinks"] = self.env["frontdesk.drink"].search_read(
                [("id", "in", self.drink_ids.ids)], ["name"]
            )
        return data

    def _get_planned_visitors(self) -> list:
        time_min = datetime.now() - timedelta(minutes=PLANNED_VISITOR_TIME)
        time_max = datetime.now() + timedelta(minutes=PLANNED_VISITOR_TIME)
        visitors = (
            self.env["frontdesk.visitor"]
            .sudo()
            .search_read(
                [
                    ("check_in", ">=", time_min),
                    ("check_in", "<=", time_max),
                    ("state", "=", "planned"),
                    ("station_id.id", "=", self.id),
                ],
                ["name", "company", "message", "host_ids"],
            )
        )
        if visitors:
            return [
                {
                    **visitor,
                    "host_ids": [
                        {"id": host.id, "name": host.name}
                        for host in self.env["hr.employee"].browse(visitor["host_ids"])
                    ],
                }
                for visitor in visitors
            ]
        return []

    def _get_tmp_code(self):
        self.check_singleton()
        return tools.hmac(
            self.env(su=True),
            MOBILE_CODE_SCOPE,
            (self.id, fields.Date.to_string(fields.Datetime.now())),
        )

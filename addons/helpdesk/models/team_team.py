import datetime
import heapq
import itertools
from collections import defaultdict
from datetime import UTC

from dateutil import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command, Domain
from odoo.tools import float_round
from odoo.tools.translate import LazyTranslate

from odoo.addons.rating.models.rating_data import RATING_LIMIT_MIN
from odoo.addons.team.models.team import TeamUsage
from odoo.addons.web.controllers.utils import clean_action

_lt = LazyTranslate(__name__)


class TeamTeam(models.Model):
    _name = "team.team"
    _inherit = ["team.team", "mixin.rating.parent"]
    _rating_satisfaction_days = 7

    def _get_or_create_default_stages(self) -> list:
        default_stages = self.env["helpdesk.stage"]
        for xml_id in [
            "stage_new",
            "stage_in_progress",
            "stage_solved",
            "stage_cancelled",
        ]:
            stage = self.env.ref("helpdesk.%s" % xml_id, raise_if_not_found=False)
            if stage:
                default_stages += stage
        if not default_stages:
            default_stages = self.env["helpdesk.stage"].create(
                {
                    "name": self.env._("New"),
                    "sequence": 0,
                    "template_id": self.env.ref(
                        "helpdesk.new_ticket_request_email_template",
                        raise_if_not_found=False,
                    ).id
                    or None,
                }
            )
        return [Command.set(default_stages.ids)]

    use_helpdesk = fields.Boolean(
        string="Helpdesk",
        help="The team handles customer tickets in the Helpdesk app.",
    )
    ticket_properties = fields.PropertiesDefinition()

    helpdesk_stage_ids = fields.Many2many(
        comodel_name="helpdesk.stage",
        relation="team_stage_rel",
        string="Stages",
        help="Stages the team will use. This team's tickets will only be able to be in these stages.",
    )
    helpdesk_auto_assignment = fields.Boolean(string="Automatic Assignment")
    helpdesk_assign_method = fields.Selection(
        selection=[
            ("randomly", "Each user is assigned an equal number of tickets"),
            ("balanced", "Each user has an equal number of open tickets"),
            ("tags", "Dispatch tickets based on tags"),
        ],
        string="Assignment Method",
        default="randomly",
        required=True,
        help="New tickets will automatically be assigned to the team members that are available, according to their working hours and their time off.",
    )
    helpdesk_privacy_visibility = fields.Selection(
        selection=[
            ("invited_internal", "Invited internal users (private)"),
            ("internal", "All internal users (company)"),
            ("portal", "Invited portal users and all internal users (public)"),
        ],
        string="Visibility",
        default="portal",
        required=True,
        help="People to whom this helpdesk team and its tickets will be visible.\n\n"
        "- Invited internal users: internal users can access the team and the tickets they are following. "
        "This access can be modified on each ticket individually by adding or removing the user as follower.\n"
        "A user with the helpdesk > administrator access right level can still access this team and its tickets, even if they are not explicitely part of the followers.\n\n"
        "- All internal users: all internal users can access the team and all of its tickets without distinction.\n\n"
        "- Invited portal users and all internal users: all internal users can access the team and all of its tickets without distinction.\n"
        "Portal users can only access the tickets they are following. "
        "This access can be modified on each ticket individually by adding or removing the portal user as follower.",
    )
    privacy_visibility_warning = fields.Char(
        export_string_translation=False,
        compute="_compute_privacy_visibility_warning",
    )
    access_instruction_message = fields.Char(
        export_string_translation=False,
        compute="_compute_access_instruction_message",
    )
    ticket_ids = fields.One2many(
        comodel_name="helpdesk.ticket",
        inverse_name="team_id",
        string="Tickets",
    )

    helpdesk_use_alias = fields.Boolean(default=True)
    helpdesk_alias_id = fields.Many2one(
        comodel_name="team.alias",
        compute="_compute_helpdesk_alias_id",
        search="_search_helpdesk_alias_id",
    )
    helpdesk_alias_name = fields.Char(
        related="helpdesk_alias_id.alias_name",
        readonly=False,
    )
    helpdesk_alias_domain_id = fields.Many2one(
        related="helpdesk_alias_id.alias_domain_id",
        readonly=False,
    )
    helpdesk_alias_domain = fields.Char(related="helpdesk_alias_id.alias_domain")
    helpdesk_alias_contact = fields.Selection(
        related="helpdesk_alias_id.alias_contact",
        readonly=False,
    )
    helpdesk_alias_email = fields.Char(related="helpdesk_alias_id.alias_full_name")
    has_external_mail_server = fields.Boolean(
        export_string_translation=False,
        compute="_compute_has_external_mail_server",
    )
    allow_portal_ticket_closing = fields.Boolean(string="Closure by Customers")
    use_website_helpdesk_form = fields.Boolean(
        string="Website Form",
        compute="_compute_use_website_helpdesk_form",
        store=True,
        readonly=False,
    )
    use_website_helpdesk_livechat = fields.Boolean(string="Live Chat")
    use_website_helpdesk_forum = fields.Boolean(
        string="Community Forum",
        compute="_compute_use_website_helpdesk_forum",
        store=True,
        readonly=False,
    )
    use_website_helpdesk_slides = fields.Boolean(
        string="eLearning",
        compute="_compute_use_website_helpdesk_slides",
        store=True,
        readonly=False,
    )
    use_website_helpdesk_knowledge = fields.Boolean(
        string="Knowledge",
        compute="_compute_use_website_helpdesk_knowledge",
        store=True,
        readonly=False,
    )
    use_helpdesk_timesheet = fields.Boolean(
        string="Timesheets",
        compute="_compute_use_helpdesk_timesheet",
        store=True,
        readonly=False,
    )
    show_knowledge_base = fields.Boolean(
        export_string_translation=False,
        compute="_compute_show_knowledge_base",
    )
    use_helpdesk_sale_timesheet = fields.Boolean(
        string="Time Billing",
        compute="_compute_use_helpdesk_sale_timesheet",
        store=True,
        readonly=False,
    )
    helpdesk_use_credit_notes = fields.Boolean(string="Refunds")
    helpdesk_use_coupons = fields.Boolean(string="Coupons")
    helpdesk_use_giftcards = fields.Boolean(string="Gift Cards")
    helpdesk_use_fsm = fields.Boolean(string="Field Service")
    helpdesk_use_product_returns = fields.Boolean(string="Returns")
    helpdesk_use_product_replacements = fields.Boolean(string="Replacements")
    helpdesk_use_product_repairs = fields.Boolean(string="Repairs")
    helpdesk_use_twitter = fields.Boolean(string="X")
    helpdesk_use_rating = fields.Boolean(string="Customer Ratings")
    helpdesk_use_sla = fields.Boolean(
        string="SLA Policies",
        default=True,
    )
    unassigned_tickets = fields.Integer(compute="_compute_unassigned_tickets")
    resource_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        string="Working Hours",
        default=lambda self: self.env.company.resource_calendar_id,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), ('schedule_type', '=', 'fully_fixed'), ('attendance_ids', '!=', False)]",
        help="Working hours used to determine the deadline of SLA Policies.",
    )
    open_ticket_count = fields.Integer(
        string="# Open Tickets",
        compute="_compute_open_ticket_count",
    )
    sla_policy_count = fields.Integer(
        string="# SLA Policy",
        compute="_compute_sla_policy_count",
    )
    ticket_closed = fields.Integer(compute="_compute_ticket_closed")
    success_rate = fields.Float(
        compute="_compute_success_rate",
        groups="helpdesk.group_use_sla",
    )
    urgent_ticket = fields.Integer(
        string="# Urgent Ticket",
        compute="_compute_urgent_ticket",
    )
    sla_failed = fields.Integer(
        string="Failed SLA Ticket",
        compute="_compute_sla_failed",
    )
    helpdesk_auto_close_ticket = fields.Boolean(string="Automatic Closing")
    helpdesk_auto_close_day = fields.Integer(
        string="Inactive Period(days)",
        default=7,
        help="Period of inactivity after which tickets will be automatically closed.",
    )
    helpdesk_from_stage_ids = fields.Many2many(
        comodel_name="helpdesk.stage",
        relation="team_stage_auto_close_from_rel",
        string="In Stages",
        domain="[('id', 'in', helpdesk_stage_ids)]",
    )
    helpdesk_to_stage_id = fields.Many2one(
        comodel_name="helpdesk.stage",
        string="Move to Stage",
        compute="_compute_assign_stage_id",
        store=True,
        readonly=False,
        domain="[('id', 'in', helpdesk_stage_ids)]",
    )
    helpdesk_alias_email_from = fields.Char(
        export_string_translation=False,
        compute="_compute_helpdesk_alias_email_from",
    )

    @api.model
    def _get_usages(self):
        return super()._get_usages() | {
            "helpdesk": TeamUsage(
                key="helpdesk",
                flag="use_helpdesk",
                label=_lt("Helpdesk"),
                manager_group="helpdesk.group_helpdesk_manager",
                alias_model="helpdesk.ticket",
            ),
        }

    @api.depends("alias_ids.usage")
    def _compute_helpdesk_alias_id(self) -> None:
        self._compute_usage_alias_field("helpdesk", "helpdesk_alias_id")

    def _search_helpdesk_alias_id(self, operator, value):
        return self._search_usage_alias_field("helpdesk", operator, value)

    @api.constrains("use_helpdesk", "company_id")
    def _check_helpdesk_company(self) -> None:
        if any(team.use_helpdesk and not team.company_id for team in self):
            raise ValidationError(self.env._("A helpdesk team belongs to a company."))

    def _check_helpdesk_members(self) -> None:
        if any(
            team.use_helpdesk
            and team.helpdesk_auto_assignment
            and team.helpdesk_assign_method != "tags"
            and not team.team_member_ids
            for team in self
        ):
            raise ValidationError(
                self.env._(
                    "A helpdesk team assigning tickets automatically needs members."
                )
            )

    @api.constrains("use_website_helpdesk_form", "helpdesk_privacy_visibility")
    def _check_website_privacy(self) -> None:
        if any(
            t.use_website_helpdesk_form and t.helpdesk_privacy_visibility != "portal"
            for t in self
        ):
            raise ValidationError(
                self.env._(
                    'Want to use the website form? Just adjust your team\'s visibility to "Invited portal users and all internal users" and watch the magic happen!'
                )
            )

    @api.depends("helpdesk_auto_close_ticket", "helpdesk_stage_ids")
    def _compute_assign_stage_id(self) -> None:
        stages_dict = {
            stage["id"]: 1 if stage["fold"] else 2
            for stage in self.env["helpdesk.stage"].search_read(
                [("id", "in", self.helpdesk_stage_ids.ids), ("fold", "=", True)],
                ["id", "fold"],
            )
        }
        for team in self:
            if not team.helpdesk_stage_ids:
                team.helpdesk_to_stage_id = False
                continue
            helpdesk_stage_ids = sorted(
                [
                    (val, stage_id)
                    for stage_id, val in stages_dict.items()
                    if stage_id in team.helpdesk_stage_ids.ids
                ]
            )
            team.helpdesk_to_stage_id = (
                helpdesk_stage_ids[0][1]
                if helpdesk_stage_ids
                else team.helpdesk_stage_ids and team.helpdesk_stage_ids.ids[-1]
            )

    def _compute_helpdesk_alias_email_from(self) -> None:
        addresses = self.sudo()._notify_get_usage_reply_to_addresses("helpdesk")
        for team in self:
            address = addresses.get(team.id)
            team.helpdesk_alias_email_from = (
                address and team._notify_get_reply_to_formatted_email(address)
            )

    def _compute_has_external_mail_server(self) -> None:
        self.has_external_mail_server = self.env.registry.settings.get(
            self.env, "base_setup.default_external_email_server", False
        )

    def _compute_unassigned_tickets(self) -> None:
        ticket_data = self.env["helpdesk.ticket"]._read_group(
            [
                ("user_id", "=", False),
                ("team_id", "in", self.ids),
                ("stage_id.fold", "=", False),
            ],
            ["team_id"],
            ["__count"],
        )
        mapped_data = {team.id: count for team, count in ticket_data}
        for team in self:
            team.unassigned_tickets = mapped_data.get(team.id, 0)

    def _compute_ticket_closed(self) -> None:
        dt = datetime.datetime.combine(
            datetime.date.today() - relativedelta.relativedelta(days=6),
            datetime.time.min,
        )
        ticket_data = self.env["helpdesk.ticket"]._read_group(
            [
                ("team_id", "in", self.ids),
                ("stage_id.fold", "=", True),
                ("close_date", ">=", dt),
            ],
            ["team_id"],
            ["__count"],
        )
        mapped_data = {team.id: count for team, count in ticket_data}
        for team in self:
            team.ticket_closed = mapped_data.get(team.id, 0)

    def _compute_success_rate(self) -> None:
        dt = datetime.datetime.combine(
            datetime.date.today() - relativedelta.relativedelta(days=6),
            datetime.time.min,
        )
        sla_teams = self.filtered("helpdesk_use_sla")
        domain = [
            ("team_id", "in", sla_teams.ids),
            "&",
            ("stage_id.fold", "=", True),
            ("close_date", ">=", dt),
        ]
        sla_tickets_and_failed_tickets_per_team = defaultdict(lambda: [0, 0])
        today = fields.Datetime.now()
        tickets_sla_count = self.env["helpdesk.ticket"]._read_group(
            domain + ["|", ("sla_reached", "=", True), ("sla_reached_late", "=", True)],
            ["team_id"],
            ["__count"],
        )
        tickets_success_count = self.env["helpdesk.ticket"]._read_group(
            domain
            + ["|", ("sla_deadline", "<", today), ("sla_reached_late", "=", True)],
            ["team_id"],
            ["__count"],
        )
        for team, team_count in tickets_sla_count:
            sla_tickets_and_failed_tickets_per_team[team.id][0] = team_count
        for team, team_count in tickets_success_count:
            sla_tickets_and_failed_tickets_per_team[team.id][1] = team_count
        for team in sla_teams:
            if not sla_tickets_and_failed_tickets_per_team.get(team.id):
                team.success_rate = -1
                continue
            total_count = sla_tickets_and_failed_tickets_per_team[team.id][0]
            success_count = (
                total_count - sla_tickets_and_failed_tickets_per_team[team.id][1]
            )
            team.success_rate = (
                float_round(success_count * 100 / total_count, 2)
                if total_count
                else 0.0
            )
        (self - sla_teams).success_rate = -1

    def _compute_urgent_ticket(self) -> None:
        ticket_data = self.env["helpdesk.ticket"]._read_group(
            [
                ("team_id", "in", self.ids),
                ("stage_id.fold", "=", False),
                ("priority", "=", 3),
            ],
            ["team_id"],
            ["__count"],
        )
        mapped_data = {team.id: count for team, count in ticket_data}
        for team in self:
            team.urgent_ticket = mapped_data.get(team.id, 0)

    def _compute_sla_failed(self) -> None:
        ticket_data = self.env["helpdesk.ticket"]._read_group(
            [
                ("team_id", "in", self.ids),
                ("stage_id.fold", "=", False),
                ("sla_fail", "=", True),
            ],
            ["team_id"],
            ["__count"],
        )
        mapped_data = {team.id: count for team, count in ticket_data}
        for team in self:
            team.sla_failed = mapped_data.get(team.id, 0)

    def _compute_open_ticket_count(self) -> None:
        ticket_data = self.env["helpdesk.ticket"]._read_group(
            [("team_id", "in", self.ids), ("stage_id.fold", "=", False)],
            ["team_id"],
            ["__count"],
        )
        mapped_data = {team.id: count for team, count in ticket_data}
        for team in self:
            team.open_ticket_count = mapped_data.get(team.id, 0)

    def _compute_sla_policy_count(self) -> None:
        sla_data = self.env["helpdesk.sla"]._read_group(
            [("team_id", "in", self.ids)], ["team_id"], ["__count"]
        )
        mapped_data = {team.id: count for team, count in sla_data}
        for team in self:
            team.sla_policy_count = mapped_data.get(team.id, 0)

    @api.onchange("helpdesk_use_alias", "name")
    def _onchange_use_alias(self) -> None:
        if not self.helpdesk_use_alias:
            self.helpdesk_alias_name = False
        if (
            self._origin.id
            and self.helpdesk_use_alias
            and not self.helpdesk_alias_name
            and self.name
        ):
            self.helpdesk_alias_name = self._get_helpdesk_unique_alias_name()

    @api.depends(
        "use_website_helpdesk_knowledge",
        "use_website_helpdesk_slides",
        "use_website_helpdesk_forum",
    )
    def _compute_use_website_helpdesk_form(self) -> None:
        teams = self.filtered(
            lambda team: (
                not team.use_website_helpdesk_form
                and (
                    team.use_website_helpdesk_knowledge
                    or team.use_website_helpdesk_slides
                    or team.use_website_helpdesk_forum
                )
            )
        )
        teams.use_website_helpdesk_form = True

    @api.depends("use_website_helpdesk_form")
    def _compute_use_website_helpdesk_forum(self) -> None:
        teams = self.filtered(
            lambda team: (
                not team.use_website_helpdesk_form and team.use_website_helpdesk_forum
            )
        )
        teams.use_website_helpdesk_forum = False

    @api.depends("use_website_helpdesk_form")
    def _compute_use_website_helpdesk_slides(self) -> None:
        teams = self.filtered(
            lambda team: (
                not team.use_website_helpdesk_form and team.use_website_helpdesk_slides
            )
        )
        teams.use_website_helpdesk_slides = False

    @api.depends("use_website_helpdesk_form")
    def _compute_use_website_helpdesk_knowledge(self) -> None:
        teams = self.filtered(
            lambda team: (
                not team.use_website_helpdesk_form
                and team.use_website_helpdesk_knowledge
            )
        )
        teams.use_website_helpdesk_knowledge = False

    @api.depends("use_helpdesk_sale_timesheet")
    def _compute_use_helpdesk_timesheet(self) -> None:
        sale_timesheet = self.filtered("use_helpdesk_sale_timesheet")
        sale_timesheet.update({"use_helpdesk_timesheet": True})

    @api.depends("use_helpdesk_timesheet")
    def _compute_use_helpdesk_sale_timesheet(self) -> None:
        without_timesheet = self.filtered(lambda t: not t.use_helpdesk_timesheet)
        without_timesheet.update({"use_helpdesk_sale_timesheet": False})

    def _compute_show_knowledge_base(self) -> None:
        self.show_knowledge_base = False

    @api.depends("helpdesk_privacy_visibility")
    def _compute_privacy_visibility_warning(self) -> None:
        for team in self:
            if not team.ids:
                team.privacy_visibility_warning = ""
            elif (
                team.helpdesk_privacy_visibility == "portal"
                and team._origin.helpdesk_privacy_visibility != "portal"
            ):
                team.privacy_visibility_warning = self.env._(
                    "Customers will be added to the followers of their tickets."
                )
            elif (
                team.helpdesk_privacy_visibility != "portal"
                and team._origin.helpdesk_privacy_visibility == "portal"
            ):
                team.privacy_visibility_warning = self.env._(
                    "Portal users will be removed from the followers of the team and its tickets."
                )
            else:
                team.privacy_visibility_warning = ""

    @api.depends("helpdesk_privacy_visibility")
    def _compute_access_instruction_message(self) -> None:
        for team in self:
            if team.helpdesk_privacy_visibility == "portal":
                team.access_instruction_message = self.env._(
                    "Grant portal users access to your helpdesk team or tickets by adding them as followers. Customers automatically get access to their tickets in their portal."
                )
            elif team.helpdesk_privacy_visibility == "invited_internal":
                team.access_instruction_message = self.env._(
                    "Grant employees access to your helpdesk team or tickets by adding them as followers. Employees automatically get access to the tickets they are assigned to."
                )
            else:
                team.access_instruction_message = ""

    def get_knowledge_base_url(self):
        self.check_singleton()
        return self.get_portal_url()

    @api.onchange("helpdesk_auto_assignment")
    def _onchange_assign_method(self) -> None:
        if self.use_helpdesk and not self.member_ids:
            self.member_ids = [Command.set(self.env.user.ids)]

    @api.depends("company_id")
    @api.depends_context("allowed_company_ids")
    def _compute_display_name(self):
        super()._compute_display_name()
        if len(self.env.context.get("allowed_company_ids", [])) <= 1:
            return
        team_default_name = self.env._("Customer Care")
        for team in self:
            if team.use_helpdesk and team.name == team_default_name:
                team.display_name = f"{team.display_name} - {team.company_id.name}"

    @api.model_create_multi
    def create(self, vals_list):
        default_use_helpdesk = self.env.context.get("default_use_helpdesk")
        for vals in vals_list:
            if not vals.get("use_helpdesk", default_use_helpdesk):
                continue
            if "helpdesk_stage_ids" not in vals:
                vals["helpdesk_stage_ids"] = self._get_or_create_default_stages()
            if not vals.get("company_id"):
                vals["company_id"] = self.env.company.id
            user = self.env.user
            if (
                "member_ids" not in vals
                and "team_member_ids" not in vals
                and user.active
                and not user.share
                and vals["company_id"] in user.company_ids.ids
            ):
                vals["member_ids"] = [Command.link(user.id)]
        teams = super().create(vals_list)
        helpdesk_teams = teams.filtered("use_helpdesk")
        if not helpdesk_teams:
            return teams
        helpdesk_teams._check_helpdesk_members()
        helpdesk_teams._set_helpdesk_default_alias_names()
        helpdesk_teams.sudo()._check_sla_group()
        helpdesk_teams.sudo()._check_rating_group()
        helpdesk_teams.sudo()._check_auto_assignment_group()
        helpdesk_teams.sudo()._check_modules_to_install()
        if helpdesk_teams.filtered("helpdesk_auto_close_ticket"):
            teams._update_cron()
        return teams

    def write(self, vals):
        if vals.get("helpdesk_privacy_visibility"):
            self.filtered("use_helpdesk")._sync_access_to_privacy_visibility(
                vals["helpdesk_privacy_visibility"]
            )
        if (
            "helpdesk_alias_name" in vals
            and not vals["helpdesk_alias_name"]
            and vals.get("helpdesk_use_alias", self.helpdesk_use_alias)
        ):
            default_alias = self.name.replace(" ", "-") if self.name else ""
            vals["helpdesk_alias_name"] = self.helpdesk_alias_name or default_alias
        if vals.get("use_helpdesk") and "helpdesk_stage_ids" not in vals:
            self.filtered(
                lambda t: not t.helpdesk_stage_ids
            ).helpdesk_stage_ids = self._get_or_create_default_stages()

        result = super().write(vals)
        helpdesk_teams = self.filtered("use_helpdesk")
        if vals.keys() & {
            "use_helpdesk",
            "member_ids",
            "team_member_ids",
            "helpdesk_auto_assignment",
            "helpdesk_assign_method",
        }:
            helpdesk_teams._check_helpdesk_members()
        if vals.get("use_helpdesk"):
            helpdesk_teams._set_helpdesk_default_alias_names()
        if "active" in vals:
            helpdesk_teams.with_context(active_test=False).mapped("ticket_ids").write(
                {"active": vals["active"]}
            )
        if "helpdesk_use_sla" in vals or "use_helpdesk" in vals:
            self.sudo()._check_sla_group()
        if "helpdesk_use_rating" in vals or "use_helpdesk" in vals:
            self.sudo()._check_rating_group()
        if "helpdesk_auto_assignment" in vals or "use_helpdesk" in vals:
            self.sudo()._check_auto_assignment_group()
        helpdesk_teams.sudo()._check_modules_to_install()
        if "helpdesk_auto_close_ticket" in vals:
            self._update_cron()
        return result

    def get_formview_id(self, access_uid=None):
        if len(self) == 1 and self._get_team_usage_keys() == ["helpdesk"]:
            return self.env.ref("helpdesk.helpdesk_team_view_form").id
        return super().get_formview_id(access_uid=access_uid)

    def unlink(self):
        stages = self.mapped("helpdesk_stage_ids").filtered(
            lambda stage: stage.team_ids <= self
        )
        stages.unlink()
        return super().unlink()

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [
            {
                **vals,
                "name": self.env._("%s (copy)", team.name),
                "member_ids": vals.get(
                    "member_ids", [Command.set(team.member_ids.ids)]
                ),
            }
            if team.use_helpdesk
            else vals
            for team, vals in zip(self, vals_list, strict=True)
        ]

    def copy_translations(self, new, excluded=()) -> None:
        if not self.use_helpdesk:
            super().copy_translations(new, excluded=excluded)
            return
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )

    def _sync_access_to_privacy_visibility(self, new_visibility) -> None:
        for team in self:
            if team.helpdesk_privacy_visibility == new_visibility:
                continue
            if new_visibility == "portal":
                for ticket in team.mapped("ticket_ids").filtered("partner_id"):
                    ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
            elif team.helpdesk_privacy_visibility == "portal":
                portal_users = team.message_partner_ids.user_ids.filtered("share")
                team.message_unsubscribe(partner_ids=portal_users.partner_id.ids)
                team.mapped("ticket_ids")._unsubscribe_portal_users()

    @api.model
    def _update_cron(self) -> None:
        cron = self.env.ref(
            "helpdesk.ir_cron_auto_close_ticket", raise_if_not_found=False
        )
        cron and cron.toggle(
            model=self._name,
            domain=[
                ("use_helpdesk", "=", True),
                ("helpdesk_auto_close_ticket", "=", True),
                ("helpdesk_auto_close_day", ">", 0),
            ],
        )

    def _get_helpdesk_user_group(self):
        return self.env.ref("helpdesk.group_helpdesk_user")

    def _get_helpdesk_use_sla_group(self):
        return self.env.ref("helpdesk.group_use_sla")

    def _get_helpdesk_use_rating_group(self):
        return self.env.ref("helpdesk.group_use_rating")

    def _is_sla_feature_enabled(self, check_user_has_group=False) -> bool:
        user_has_group = (
            self.env.user.has_group("helpdesk.group_use_sla")
            if check_user_has_group
            else True
        )
        return bool(
            user_has_group
            and self.env["team.team"].search(
                [("use_helpdesk", "=", True), ("helpdesk_use_sla", "=", True)], limit=1
            )
        )

    def _is_rating_feature_enabled(self, check_user_has_group=False) -> bool:
        user_has_group = (
            self.env.user.has_group("helpdesk.group_use_rating")
            if check_user_has_group
            else True
        )
        return bool(
            user_has_group
            and self.env["team.team"].search(
                [("use_helpdesk", "=", True), ("helpdesk_use_rating", "=", True)],
                limit=1,
            )
        )

    def _check_sla_group(self) -> None:
        helpdesk_teams = self.filtered("use_helpdesk")
        sla_teams = helpdesk_teams.filtered("helpdesk_use_sla")
        non_sla_teams = helpdesk_teams - sla_teams
        use_sla_group = helpdesk_user_group = None
        user_has_use_sla_group = self.env.user.has_group("helpdesk.group_use_sla")

        if sla_teams:
            if not user_has_use_sla_group:
                use_sla_group = self._get_helpdesk_use_sla_group()
                helpdesk_user_group = self._get_helpdesk_user_group()
                helpdesk_user_group.write(
                    {"implied_ids": [Command.link(use_sla_group.id)]}
                )
            self.env["helpdesk.sla"].with_context(active_test=False).search(
                [
                    ("team_id", "in", sla_teams.ids),
                    ("active", "=", False),
                ]
            ).write({"active": True})

        if non_sla_teams:
            self.env["helpdesk.sla"].search(
                [("team_id", "in", non_sla_teams.ids)]
            ).write({"active": False})
            if user_has_use_sla_group and not self._is_sla_feature_enabled():
                use_sla_group = use_sla_group or self._get_helpdesk_use_sla_group()
                helpdesk_user_group = (
                    helpdesk_user_group or self._get_helpdesk_user_group()
                )
                helpdesk_user_group.write(
                    {"implied_ids": [Command.unlink(use_sla_group.id)]}
                )
                self.env["res.users.grant"]._revoke(
                    None, use_sla_group, reason="no team uses the feature"
                )

    def _check_rating_group(self) -> None:
        helpdesk_teams = self.filtered("use_helpdesk")
        rating_teams = helpdesk_teams.filtered("helpdesk_use_rating")
        user_has_use_rating_group = self.env.user.has_group("helpdesk.group_use_rating")
        rating_helpdesk_email_template = self.env.ref(
            "helpdesk.rating_ticket_request_email_template"
        )

        if rating_teams and not user_has_use_rating_group:
            self._get_helpdesk_user_group().write(
                {
                    "implied_ids": [
                        Command.link(self._get_helpdesk_use_rating_group().id)
                    ]
                }
            )
            if not rating_helpdesk_email_template.active:
                rating_helpdesk_email_template.active = True
        elif (
            helpdesk_teams - rating_teams
            and user_has_use_rating_group
            and not self._is_rating_feature_enabled()
        ):
            use_rating_group = self._get_helpdesk_use_rating_group()
            self._get_helpdesk_user_group().write(
                {"implied_ids": [Command.unlink(use_rating_group.id)]}
            )
            self.env["res.users.grant"]._revoke(
                None, use_rating_group, reason="no team uses the feature"
            )
            if rating_helpdesk_email_template.active:
                rating_helpdesk_email_template.active = False
            self.env["helpdesk.stage"].search(
                [
                    (
                        "template_id",
                        "=",
                        self.env.ref(
                            "helpdesk.rating_ticket_request_email_template"
                        ).id,
                    )
                ]
            ).template_id = False

    def _check_auto_assignment_group(self) -> None:
        has_auto_assignment_group = self.env.user.has_group(
            "helpdesk.group_auto_assignment"
        )
        has_auto_assignment = self.env["team.team"].search_count(
            [("use_helpdesk", "=", True), ("helpdesk_auto_assignment", "=", True)],
            limit=1,
        )
        group_auto_assignment = self.env.ref("helpdesk.group_auto_assignment")
        if has_auto_assignment and not has_auto_assignment_group:
            self._get_helpdesk_user_group().write(
                {"implied_ids": [Command.link(group_auto_assignment.id)]}
            )
        elif not has_auto_assignment and has_auto_assignment_group:
            self._get_helpdesk_user_group().write(
                {"implied_ids": [Command.unlink(group_auto_assignment.id)]}
            )
            self.env["res.users.grant"]._revoke(
                None, group_auto_assignment, reason="no team uses the feature"
            )

    def _get_field_check_method(self):
        return {
            "helpdesk_use_sla": self._is_sla_feature_enabled,
            "helpdesk_use_rating": self._is_rating_feature_enabled,
        }

    @api.model
    def _get_field_modules(self) -> dict:
        return {
            "use_website_helpdesk_form": "website_helpdesk",
            "use_website_helpdesk_livechat": "website_helpdesk_livechat",
            "use_website_helpdesk_forum": "website_helpdesk_forum",
            "use_website_helpdesk_slides": "website_helpdesk_slides",
            "use_website_helpdesk_knowledge": "website_helpdesk_knowledge",
            "use_helpdesk_timesheet": "helpdesk_timesheet",
            "use_helpdesk_sale_timesheet": "helpdesk_sale_timesheet",
            "helpdesk_use_credit_notes": "helpdesk_account",
            "helpdesk_use_product_returns": "helpdesk_stock",
            "helpdesk_use_product_replacements": "helpdesk_stock",
            "helpdesk_use_product_repairs": "helpdesk_repair",
            "helpdesk_use_coupons": "helpdesk_sale_loyalty",
            "helpdesk_use_giftcards": "helpdesk_sale_loyalty",
            "helpdesk_use_fsm": "helpdesk_fsm",
        }

    @api.model
    def get_features_enabled(self, updated_features=None):
        if not self.env.user.has_group("helpdesk.group_helpdesk_user"):
            return {}
        if updated_features is None:
            return {
                key: bool(check_method())
                for key, check_method in self._get_field_check_method().items()
            }
        return {
            key: bool(check_method())
            for key, check_method in self._get_field_check_method().items()
            if updated_features and key in updated_features
        }

    @api.model
    def check_modules_to_install(self, enabled_features) -> bool:
        if not enabled_features:
            return False
        module_names = [
            module_name
            for fname, module_name in self._get_field_modules().items()
            if fname in enabled_features
        ]
        if module_names:
            return bool(
                self.env["ir.module.module"].search_count(
                    [
                        ("name", "in", module_names),
                        ("state", "not in", ("installed", "to install", "to upgrade")),
                    ],
                    limit=1,
                )
            )
        return False

    def _check_modules_to_install(self) -> bool:
        expected = [
            mname
            for fname, mname in self._get_field_modules().items()
            if any(team[fname] for team in self)
        ]
        modules = self.env["ir.module.module"]
        if expected:
            STATES = ("installed", "to install", "to upgrade")
            modules = modules.search([("name", "in", expected)])
            modules = modules.filtered(lambda module: module.state not in STATES)

        if modules:
            modules.button_immediate_install()

        return bool(modules)

    def _get_helpdesk_unique_alias_name(self):
        self.check_singleton()
        base_email_alias = (self.name or "").lower().replace(" ", "-")
        return self._get_unique_email_alias(base_email_alias)

    def _set_helpdesk_default_alias_names(self) -> None:
        for team in self.filtered(
            lambda t: t.helpdesk_use_alias and t.helpdesk_alias_id and t.name
        ):
            if not team.helpdesk_alias_name:
                team.helpdesk_alias_name = team._get_helpdesk_unique_alias_name()

    def _get_unique_email_alias(self, email_alias):
        existing_aliases = self._get_existing_email_aliases(email_alias)
        modified_email_alias = email_alias
        counter = 2
        while modified_email_alias in existing_aliases:
            modified_email_alias = f"{email_alias}-{counter}"
            counter += 1
        return self.env["mail.alias"]._normalize_alias_name(modified_email_alias)

    def _get_existing_email_aliases(self, email_alias) -> set:
        existing_aliases = self.env["mail.alias"].search(
            [("alias_name", "ilike", email_alias)]
        )
        return {alias.alias_name for alias in existing_aliases}

    @api.model
    def get_dashboard(self):
        user_uses_sla = self._is_sla_feature_enabled(check_user_has_group=True)

        HelpdeskTicket = self.env["helpdesk.ticket"]
        show_demo = not bool(HelpdeskTicket.search([], limit=1))
        result = {
            "helpdesk_target_closed": self.env.user.helpdesk_target_closed,
            "helpdesk_target_rating": self.env.user.helpdesk_target_rating,
            "helpdesk_target_success": self.env.user.helpdesk_target_success,
            "today": {"sla_ticket_count": 0, "count": 0, "rating": 0, "success": 0},
            "7days": {"sla_ticket_count": 0, "count": 0, "rating": 0, "success": 0},
            "my_all": {"count": 0, "hours": 0, "failed": 0},
            "my_high": {"count": 0, "hours": 0, "failed": 0},
            "my_urgent": {"count": 0, "hours": 0, "failed": 0},
            "show_demo": show_demo,
            "rating_enable": False,
            "success_rate_enable": user_uses_sla,
        }

        if show_demo:
            result.update(
                {
                    "my_all": {"count": 10, "hours": 30, "failed": 4},
                    "my_high": {"count": 3, "hours": 10, "failed": 2},
                    "my_urgent": {"count": 2, "hours": 15, "failed": 1},
                    "today": {
                        "sla_ticket_count": 1,
                        "count": 1,
                        "rating": 2.5,
                        "success": 50,
                    },
                    "7days": {
                        "sla_ticket_count": 1,
                        "count": 15,
                        "rating": 3.5,
                        "success": 80,
                    },
                    "helpdesk_target_rating": 3.5,
                    "helpdesk_target_success": 85,
                    "helpdesk_target_closed": 12,
                }
            )
            return result

        def _is_sla_failed(data) -> bool:
            deadline = data.get("sla_deadline")
            sla_deadline = fields.Datetime.now() > deadline if deadline else False
            return bool(sla_deadline or data.get("sla_reached_late"))

        def add_to(ticket, key="my_all"):
            result[key]["count"] += 1
            result[key]["hours"] += ticket["open_hours"]
            if _is_sla_failed(ticket):
                result[key]["failed"] += 1

        domain = Domain("user_id", "=", self.env.uid)
        tickets = HelpdeskTicket.search_read(
            domain & Domain("stage_id.fold", "=", False),
            ["sla_deadline", "open_hours", "sla_reached_late", "priority"],
        )
        for ticket in tickets:
            add_to(ticket, "my_all")
            if ticket["priority"] == "2":
                add_to(ticket, "my_high")
            if ticket["priority"] == "3":
                add_to(ticket, "my_urgent")

        group_fields = []
        if user_uses_sla:
            group_fields = ["sla_reached_late", "sla_reached"]

        today = self._local_midnight_as_utc()
        tickets = HelpdeskTicket._read_group(
            domain + [("stage_id.fold", "=", True), ("close_date", ">=", today)],
            group_fields,
            ["__count"],
        )
        for row in tickets:
            if not user_uses_sla:
                [count] = row
            else:
                sla_reached_late, sla_reached, count = row
                if sla_reached or sla_reached_late:
                    result["today"]["sla_ticket_count"] += count
                    if not sla_reached_late:
                        result["today"]["success"] += count
            result["today"]["count"] += count

        dt = fields.Datetime.to_string(today - relativedelta.relativedelta(days=6))
        tickets = HelpdeskTicket._read_group(
            domain + [("stage_id.fold", "=", True), ("close_date", ">=", dt)],
            group_fields,
            ["__count"],
        )
        for row in tickets:
            if not user_uses_sla:
                [count] = row
            else:
                sla_reached_late, sla_reached, count = row
                if sla_reached or sla_reached_late:
                    result["7days"]["sla_ticket_count"] += count
                    if not sla_reached_late:
                        result["7days"]["success"] += count
            result["7days"]["count"] += count

        result["today"]["success"] = fields.Float.round(
            result["today"]["success"]
            * 100
            / (result["today"]["sla_ticket_count"] or 1),
            2,
        )
        result["7days"]["success"] = fields.Float.round(
            result["7days"]["success"]
            * 100
            / (result["7days"]["sla_ticket_count"] or 1),
            2,
        )
        result["my_all"]["hours"] = fields.Float.round(
            result["my_all"]["hours"] / (result["my_all"]["count"] or 1), 2
        )
        result["my_high"]["hours"] = fields.Float.round(
            result["my_high"]["hours"] / (result["my_high"]["count"] or 1), 2
        )
        result["my_urgent"]["hours"] = fields.Float.round(
            result["my_urgent"]["hours"] / (result["my_urgent"]["count"] or 1), 2
        )

        if self._is_rating_feature_enabled(check_user_has_group=True):
            result["rating_enable"] = True
            domain = [("user_id", "=", self.env.uid)]
            one_week_before = today - relativedelta.relativedelta(weeks=1)
            helpdesk_ratings = self.env["rating.rating"].search(
                [
                    ("res_model", "=", "helpdesk.ticket"),
                    ("res_id", "!=", False),
                    ("write_date", ">", fields.Datetime.to_string(one_week_before)),
                    ("write_date", "<=", self.env.cr.now()),
                    ("rating", ">=", RATING_LIMIT_MIN),
                    ("consumed", "=", True),
                ]
            )
            tickets = HelpdeskTicket.search(
                [
                    ("id", "in", helpdesk_ratings.mapped("res_id")),
                    ("user_id", "=", self.env.uid),
                ]
            )
            today_rating_stat = {"count": 0.0, "score": 0.0}
            rating_stat = {**today_rating_stat}
            for rating in helpdesk_ratings:
                if rating.res_id not in tickets.ids:
                    continue
                if rating.write_date >= today:
                    today_rating_stat["count"] += 1
                    today_rating_stat["score"] += rating.rating
                rating_stat["score"] += rating.rating
                rating_stat["count"] += 1

            def average_score(d):
                return fields.Float.round(
                    d["score"] / d["count"] if d["count"] > 0 else 0.0, 2
                )

            result["today"]["rating"] = average_score(today_rating_stat)
            result["7days"]["rating"] = average_score(rating_stat)
        return result

    def _action_view_rating(
        self, period=False, only_closed_tickets=False, user_id=None
    ):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "helpdesk.rating_rating_action_helpdesk"
        )
        action = clean_action(action, self.env)
        domain = [("team_id", "in", self.ids)]
        context = dict(
            self.env["ir.actions.actions"]._eval_action_context(
                action.get("context", {})
            ),
            search_default_my_ratings=True,
        )
        update_views = {}
        if period == "seven_days":
            domain += [
                (
                    "close_date",
                    ">=",
                    fields.Datetime.to_string(
                        self._local_midnight_as_utc()
                        - relativedelta.relativedelta(days=6)
                    ),
                )
            ]
            update_views[
                self.env.ref(
                    "helpdesk.rating_rating_view_seven_days_pivot_inherit_helpdesk"
                ).id
            ] = "pivot"
            update_views[
                self.env.ref(
                    "helpdesk.rating_rating_view_seven_days_graph_inherit_helpdesk"
                ).id
            ] = "graph"
            context["search_default_filter_rated_on"] = "custom_rated_on_last_7_days"
        elif period == "today":
            context["search_default_filter_rated_on"] = "custom_rated_on_today"
            if "__count__" in context.get("pivot_measures", {}):
                context.get("pivot_measures").remove("__count__")
            domain += [
                (
                    "close_date",
                    ">=",
                    fields.Datetime.to_string(self._local_midnight_as_utc()),
                )
            ]
            update_views[
                self.env.ref(
                    "helpdesk.rating_rating_view_today_pivot_inherit_helpdesk"
                ).id
            ] = "pivot"
            update_views[
                self.env.ref(
                    "helpdesk.rating_rating_view_today_graph_inherit_helpdesk"
                ).id
            ] = "graph"
        action["views"] = [
            (state, view)
            for state, view in action["views"]
            if view not in update_views.values()
        ] + list(update_views.items())
        if only_closed_tickets:
            domain += [("stage_id.fold", "=", True)]
        if user_id:
            domain += [("user_id", "=", user_id)]

        ticket_ids = self.env["helpdesk.ticket"].search(domain).ids
        action.update(
            {
                "context": context,
                "domain": [
                    ("res_id", "in", ticket_ids),
                    ("rating", ">=", RATING_LIMIT_MIN),
                    ("res_model", "=", "helpdesk.ticket"),
                    ("consumed", "=", True),
                ],
            }
        )
        return action

    def action_view_ticket(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "helpdesk.helpdesk_ticket_action_team"
        )
        action["display_name"] = self.name
        return action

    def _get_action_view_ticket_params(self, is_ticket_closed=False) -> dict:
        domain = Domain("team_id", "in", self.ids)

        context = {
            "search_default_is_open": not is_ticket_closed,
            "default_team_id": self.id,
        }
        view_mode = "list,kanban,form,activity,pivot,graph,cohort"
        if is_ticket_closed:
            domain &= Domain(
                "close_date",
                ">=",
                self._local_midnight_as_utc() - datetime.timedelta(days=6),
            )
            context.update(search_default_closed_on="custom_closed_on_last_7_days")
        return {
            "domain": domain,
            "context": context,
            "view_mode": view_mode,
        }

    def action_view_closed_ticket(self):
        action = self.action_view_ticket()
        action_params = self._get_action_view_ticket_params(True)
        action.update(
            {
                **action_params,
                "domain": Domain.AND(
                    [action_params["domain"], [("stage_id.fold", "=", True)]]
                ),
            }
        )
        return action

    def action_view_success_rate(self):
        action = self.action_view_ticket()
        action_params = self._get_action_view_ticket_params(True)
        action.update(
            domain=Domain.AND(
                [
                    action_params["domain"],
                    [("team_id", "in", self.ids), ("stage_id.fold", "=", True)],
                ]
            ),
            context={
                **action_params["context"],
                "search_default_sla_success": True,
            },
            view_mode=action_params["view_mode"],
            views=[(False, view) for view in action_params["view_mode"].split(",")],
        )
        return action

    def action_view_customer_satisfaction(self):
        action = self._action_view_rating(period="seven_days")
        action["context"] = {
            **self.env.context,
            **action["context"],
            "search_default_my_ratings": False,
        }
        return action

    def action_view_open_ticket(self):
        action = self.action_view_ticket()
        action_params = self._get_action_view_ticket_params()
        action.update(
            {
                "context": action_params["context"],
                "domain": action_params["domain"],
            }
        )
        return action

    def action_view_urgent(self):
        action = self.action_view_ticket()
        action_params = self._get_action_view_ticket_params()
        action.update(
            {
                "context": {
                    **action_params["context"],
                    "search_default_urgent_priority": True,
                },
            }
        )
        return action

    def action_view_sla_failed(self):
        action = self.action_view_ticket()
        action_params = self._get_action_view_ticket_params()
        action.update(
            {
                "context": {
                    **action_params["context"],
                    "search_default_sla_failed": True,
                },
                "domain": Domain.AND(
                    [action_params["domain"], [("sla_fail", "=", True)]]
                ),
            }
        )
        return action

    def action_view_rating_today(self):
        return self.search(
            [("use_helpdesk", "=", True), ("member_ids", "in", self.env.uid)]
        )._action_view_rating(period="today", user_id=self.env.uid)

    def action_view_rating_7days(self):
        return self.search(
            [("use_helpdesk", "=", True), ("member_ids", "in", self.env.uid)]
        )._action_view_rating(period="seven_days", user_id=self.env.uid)

    def action_view_team_rating(self):
        self.check_singleton()
        action = self._action_view_rating()
        ratings = self.env["rating.rating"].search(action["domain"])
        if len(ratings) == 1:
            action.update(
                {"view_mode": "form", "views": [(False, "form")], "res_id": ratings.id}
            )
        else:
            action["context"] = {
                "search_default_filter_create_date": "custom_create_date_last_30_days"
            }
        return action

    def action_view_open_ticket_view(self):
        action = self.action_view_ticket()
        action.update(
            {
                "display_name": self.env._("Tickets"),
                "domain": [("team_id", "=", self.id), ("stage_id.fold", "=", False)],
            }
        )
        return action

    def action_view_sla_policy(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "helpdesk.helpdesk_sla_action"
        )
        if self.sla_policy_count == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": self.env["helpdesk.sla"]
                    .search([("team_id", "=", self.id)], limit=1)
                    .id,
                    "views": [(False, "form")],
                }
            )
        action.update(
            {
                "context": {"default_team_id": self.id},
                "domain": [("team_id", "=", self.id)],
            }
        )
        return action

    def _get_user_to_assign(self, count_per_team):
        team_without_manually = self.env["team.team"].browse(
            {
                team.id
                for team in count_per_team
                if team.helpdesk_auto_assignment
                and team.helpdesk_assign_method in ["randomly", "balanced"]
            }
        )
        result = {team.id: [False] * count for team, count in count_per_team.items()}
        team_without_manually = team_without_manually.sudo()
        users_per_working_days = team_without_manually.member_ids.with_env(
            self.env
        )._get_working_users_per_first_working_day()
        for team in team_without_manually:
            if not team.member_ids:
                continue
            count = count_per_team[team]
            member_ids = team.member_ids.ids
            for user_ids in users_per_working_days:
                if any(user_id in member_ids for user_id in user_ids):
                    member_ids = [
                        user_id for user_id in user_ids if user_id in member_ids
                    ]
                    break

            if team.helpdesk_assign_method == "randomly":
                last_assigned_user = (
                    self.env["helpdesk.ticket"]
                    .search(
                        [("team_id", "=", team.id), ("user_id", "!=", False)],
                        order="create_date desc, id desc",
                        limit=1,
                    )
                    .user_id
                )
                offset = 0
                if last_assigned_user:
                    for member in team.member_ids:
                        if member.id in member_ids:
                            offset = (offset + 1) % len(member_ids)
                        if member == last_assigned_user:
                            break
                result[team.id] = list(
                    itertools.islice(
                        itertools.cycle(member_ids), offset, offset + count
                    )
                )
            elif team.helpdesk_assign_method == "balanced":
                ticket_count_data = self.env["helpdesk.ticket"]._read_group(
                    [
                        ("stage_id.fold", "=", False),
                        ("user_id", "in", member_ids),
                        ("team_id", "=", team.id),
                    ],
                    ["user_id"],
                    ["__count"],
                )
                open_ticket_per_user_map = dict.fromkeys(member_ids, 0)
                open_ticket_per_user_map.update(
                    (user.id, count) for user, count in ticket_count_data
                )
                selected_user_ids = []
                heap = [
                    (open_tickets, user_id)
                    for user_id, open_tickets in open_ticket_per_user_map.items()
                ]
                heapq.heapify(heap)
                for _dummy in range(count):
                    open_tickets, user_id = heapq.heappop(heap)
                    selected_user_ids.append(user_id)
                    heapq.heappush(heap, (open_tickets + 1, user_id))
                result[team.id] = selected_user_ids
        return result

    def _get_stage(self):
        result = dict.fromkeys(self.ids, self.env["helpdesk.stage"])
        for team in self:
            result[team.id] = self.env["helpdesk.stage"].search(
                [("team_ids", "in", team.id)], order="sequence", limit=1
            )
        return result

    def _get_closing_stage(self):
        closed_stage = self.helpdesk_stage_ids.filtered(lambda stage: stage.fold)
        if not closed_stage:
            closed_stage = self.helpdesk_stage_ids[-1]
        return closed_stage

    def _cron_auto_close_tickets(self) -> None:
        teams = self.env["team.team"].search_read(
            domain=[
                ("use_helpdesk", "=", True),
                ("helpdesk_auto_close_ticket", "=", True),
                ("helpdesk_auto_close_day", ">", 0),
                ("helpdesk_to_stage_id", "!=", False),
            ],
            fields=[
                "id",
                "helpdesk_auto_close_day",
                "helpdesk_from_stage_ids",
                "helpdesk_to_stage_id",
            ],
        )
        teams_dict = defaultdict(dict)
        today = fields.Datetime.today()
        for team in teams:
            team["threshold_date"] = today - relativedelta.relativedelta(
                days=team["helpdesk_auto_close_day"]
            )
            teams_dict[team["id"]] = team
        tickets_domain = [
            ("stage_id.fold", "=", False),
            ("team_id", "in", list(teams_dict.keys())),
        ]
        tickets = self.env["helpdesk.ticket"].search(tickets_domain)

        def is_inactive_ticket(ticket) -> bool:
            team = teams_dict[ticket.team_id.id]
            is_write_date_ok = ticket.write_date <= team["threshold_date"]
            if team["helpdesk_from_stage_ids"]:
                is_stage_ok = ticket.stage_id.id in team["helpdesk_from_stage_ids"]
            else:
                is_stage_ok = not ticket.stage_id.fold
            return bool(is_write_date_ok and is_stage_ok)

        inactive_tickets = tickets.filtered(is_inactive_ticket)
        for ticket in inactive_tickets:
            if teams_dict[ticket.team_id.id]["helpdesk_to_stage_id"]:
                ticket.write(
                    {
                        "stage_id": teams_dict[ticket.team_id.id][
                            "helpdesk_to_stage_id"
                        ][0]
                    }
                )

    def _local_midnight_as_utc(self):
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        return (
            datetime.datetime.combine(now.date(), datetime.time.min, now.tzinfo)
            .astimezone(UTC)
            .replace(tzinfo=None)
        )

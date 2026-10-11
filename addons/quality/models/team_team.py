from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools.translate import LazyTranslate

from odoo.addons.team.models.team import TeamUsage

_lt = LazyTranslate(__name__)


_debug = DebugLog(__name__)


class TeamTeam(models.Model):
    _inherit = "team.team"

    use_quality = fields.Boolean(
        string="Quality",
        help="The team controls quality: it owns quality points, checks and alerts.",
    )
    quality_check_count = fields.Integer(
        string="# Quality Checks",
        compute="_compute_quality_check_count",
        groups="quality.group_quality_user",
    )
    quality_alert_count = fields.Integer(
        string="# Quality Alerts",
        compute="_compute_quality_alert_count",
        groups="quality.group_quality_user",
    )
    quality_check_ids = fields.One2many(
        comodel_name="quality.check",
        inverse_name="team_id",
        string="Quality Checks",
    )
    quality_alert_ids = fields.One2many(
        comodel_name="quality.alert",
        inverse_name="team_id",
        string="Quality Alerts",
    )
    quality_alias_id = fields.Many2one(
        comodel_name="team.alias",
        compute="_compute_quality_alias_id",
        search="_search_quality_alias_id",
    )
    quality_alias_name = fields.Char(
        related="quality_alias_id.alias_name",
        string="Quality Alias Name",
        readonly=False,
    )
    quality_alias_domain_id = fields.Many2one(
        related="quality_alias_id.alias_domain_id",
        string="Quality Alias Domain",
        readonly=False,
    )
    quality_alias_email = fields.Char(
        related="quality_alias_id.alias_full_name",
        string="Quality Email Alias",
    )

    @api.model
    def _get_usages(self):
        return super()._get_usages() | {
            "quality": TeamUsage(
                key="quality",
                flag="use_quality",
                label=_lt("Quality"),
                manager_group="quality.group_quality_manager",
                alias_model="quality.alert",
            ),
        }

    def _prepare_usage_alias_defaults(self, key):
        defaults = super()._prepare_usage_alias_defaults(key)
        if key == "quality":
            defaults["company_id"] = self.company_id.id
        return defaults

    @api.depends("alias_ids.usage")
    def _compute_quality_alias_id(self) -> None:
        self._compute_usage_alias_field("quality", "quality_alias_id")

    def _search_quality_alias_id(self, operator, value):
        return self._search_usage_alias_field("quality", operator, value)

    @api.depends("quality_check_ids.quality_state")
    def _compute_quality_check_count(self) -> None:
        _debug.perf.count("team_quality_check_count", teams=self)
        check_data = self.env["quality.check"]._read_group(
            [("team_id", "in", self.ids), ("quality_state", "=", "none")],
            ["team_id"],
            ["__count"],
        )
        check_result = {team.id: count for team, count in check_data}
        for team in self:
            team.quality_check_count = check_result.get(team.id, 0)

    @api.depends("quality_alert_ids.stage_id.done")
    def _compute_quality_alert_count(self) -> None:
        _debug.perf.count("team_quality_alert_count", teams=self)
        alert_data = self.env["quality.alert"]._read_group(
            [("team_id", "in", self.ids), ("stage_id.done", "=", False)],
            ["team_id"],
            ["__count"],
        )
        alert_result = {team.id: count for team, count in alert_data}
        for team in self:
            team.quality_alert_count = alert_result.get(team.id, 0)

    @api.model
    def _get_quality_team(self, domain):
        _debug.logic("quality_team_resolve", teams=self)
        team_id = self.search([("use_quality", "=", True), *domain], limit=1).id
        if team_id:
            return team_id
        raise UserError(
            self.env._(
                "No quality teams found for this company! Head over to the configuration menu to create your first quality team."
            )
        )

    @api.model
    def _get_default_quality_team_for(self, record):
        _debug.logic("quality_team_default", teams=self)
        company_id = record.company_id.id or self.env.context.get(
            "default_company_id", self.env.company.id
        )
        return self._get_quality_team(self._check_company_domain(company_id))

from odoo import api, fields, models
from odoo.tools import frozendict

from odoo.addons.helpdesk.models.helpdesk_ticket import TICKET_PRIORITY


class HelpdeskSla(models.Model):
    _name = "helpdesk.sla"
    _order = "name"
    _description = "Helpdesk SLA Policies"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    @api.model
    def default_get(self, fields):
        defaults = self.env["team.team"]._drop_default_of_other_usage(
            super().default_get(fields), "helpdesk"
        )
        if "team_id" in fields or "stage_id" in fields:
            team = self.env["team.team"].browse(defaults.get("team_id"))
            if not team:
                defaults["team_id"] = team.id
                team = self.env["team.team"].search(
                    [("use_helpdesk", "=", True)], limit=1
                )
            stage_ids = (
                team.helpdesk_stage_ids.filtered("fold").ids[:1]
                or team.helpdesk_stage_ids.ids[-1:]
            )
            defaults["stage_id"] = stage_ids[0] if stage_ids else False
        return defaults

    name = fields.Char(
        translate=True,
        required=True,
    )
    description = fields.Html(
        string="SLA Policy Description",
        translate=True,
    )
    active = fields.Boolean(default=True)
    team_id = fields.Many2one(
        comodel_name="team.team",
        string="Helpdesk Team",
        required=True,
        domain=[("use_helpdesk", "=", True)],
    )
    tag_ids = fields.Many2many(
        comodel_name="helpdesk.tag",
        string="Tags",
    )
    stage_id = fields.Many2one(
        comodel_name="helpdesk.stage",
        string="Target Stage",
        help="Minimum stage a ticket needs to reach in order to satisfy this SLA.",
    )
    exclude_stage_ids = fields.Many2many(
        comodel_name="helpdesk.stage",
        string="Excluding Stages",
        copy=True,
        domain="[('id', '!=', stage_id.id)]",
        help="The time spent in these stages won't be taken into account in the calculation of the SLA.",
    )
    priority = fields.Selection(
        selection=TICKET_PRIORITY,
        default="0",
        required=True,
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Customers",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="team_id.company_id",
        string="Company",
        readonly=True,
    )
    time = fields.Float(
        string="Within",
        default=0,
        required=True,
        help="Maximum number of working hours a ticket should take to reach the target stage, starting from the date it was created.",
    )
    ticket_count = fields.Integer(compute="_compute_ticket_count")

    def _compute_ticket_count(self) -> None:
        res = self.env["helpdesk.ticket"]._read_group(
            [("sla_ids", "in", self.ids), ("stage_id.fold", "=", False)],
            ["sla_ids"],
            ["__count"],
        )
        sla_data = {sla.id: count for sla, count in res}
        for sla in self:
            sla.ticket_count = sla_data.get(sla.id, 0)

    @api.depends("team_id")
    @api.depends_context("with_team_name")
    def _compute_display_name(self):
        if not self.env.context.get("with_team_name"):
            return super()._compute_display_name()
        for sla in self:
            sla.display_name = f"{sla.name} - {sla.team_id.name}"
        return None

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [
            dict(vals, name=self.env._("%s (copy)", sla.name))
            for sla, vals in zip(self, vals_list, strict=False)
        ]

    def copy_translations(self, new, excluded=()) -> None:
        # ``copy_data`` renames ``name`` in the duplicating user's language
        # only; without this the copy would keep the source record's exact
        # ``name`` in every other language.
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )

    def action_view_helpdesk_ticket(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "helpdesk.helpdesk_ticket_action_main_tree"
        )
        action.update(
            {
                "domain": [("sla_ids", "in", self.ids)],
                "context": {
                    "search_default_is_open": True,
                    "create": False,
                },
            }
        )
        return action

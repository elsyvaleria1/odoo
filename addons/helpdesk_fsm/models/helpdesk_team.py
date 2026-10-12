from odoo import api, fields, models


class HelpdeskTeam(models.Model):
    _inherit = "team.team"

    fsm_project_id = fields.Many2one(
        comodel_name="project.project",
        string="FSM Project",
        compute="_compute_fsm_project_id",
        store=True,
        readonly=False,
        domain=[("is_fsm", "=", True), ("is_template", "=", False)],
    )

    @api.depends("helpdesk_use_fsm", "company_id")
    def _compute_fsm_project_id(self) -> None:
        fsm_teams_without_project = self.filtered(
            lambda t: t.helpdesk_use_fsm and not t.fsm_project_id
        )
        if fsm_teams_without_project:
            mapped_project_per_company = dict(
                self.env["project.project"]._read_group(
                    domain=[
                        ("is_fsm", "=", True),
                        ("company_id", "in", fsm_teams_without_project.company_id.ids),
                    ],
                    groupby=["company_id"],
                    aggregates=["id:min"],
                )
            )
            for team in fsm_teams_without_project:
                team.fsm_project_id = mapped_project_per_company.get(
                    team.company_id, False
                )
        (self - fsm_teams_without_project).fsm_project_id = False

    def _mail_get_message_subtypes(self):
        res = super()._mail_get_message_subtypes()
        if len(self) == 1:
            task_done_subtype = self.env.ref("helpdesk_fsm.mt_team_ticket_task_done")
            if not self.helpdesk_use_fsm and task_done_subtype in res:
                res -= task_done_subtype
        return res

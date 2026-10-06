from odoo import fields, models
from odoo.tools import frozendict


class ReportProjectTaskUserFsm(models.Model):
    _name = "report.project.task.user.fsm"
    _inherit = ["report.project.task.user"]
    _description = "FSM Tasks Analysis"
    _auto = False
    _depends = frozendict(
        {
            "project.project": ["is_fsm"],
            "project.task": [
                "allocated_hours",
                "company_id",
                "create_date",
                "date_assign",
                "date_closed",
                "date_end",
                "date_last_status_change",
                "date_start",
                "description",
                "display_in_project",
                "effective_hours",
                "has_template_ancestor",
                "is_template",
                "lead_time_days",
                "lead_time_hours",
                "lost_reason_id",
                "milestone_id",
                "name",
                "overtime",
                "parent_id",
                "partner_id",
                "planned_hours",
                "priority",
                "project_id",
                "queue_time_days",
                "queue_time_hours",
                "rating_last_value",
                "remaining_hours",
                "state",
                "step_id",
            ],
            "rating.rating": ["consumed", "rating", "res_id", "res_model"],
            "res.partner": [
                "city",
                "country_id",
                "state_id",
                "street",
                "street2",
                "zip",
            ],
        }
    )

    partner_zip = fields.Char(
        string="ZIP",
        readonly=True,
    )
    partner_city = fields.Char(
        string="City",
        readonly=True,
    )
    partner_street = fields.Char(
        string="Street",
        readonly=True,
    )
    partner_street2 = fields.Char(
        string="Street2",
        readonly=True,
    )
    partner_country_id = fields.Many2one(
        comodel_name="res.country",
        string="Country",
        readonly=True,
    )
    partner_state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="Customer State",
        readonly=True,
    )

    def _select(self):
        return (
            super()._select()
            + """,
            rp.zip AS partner_zip,
            rp.city AS partner_city,
            rp.street AS partner_street,
            rp.street2 AS partner_street2,
            rp.country_id AS partner_country_id,
            rp.state_id AS partner_state_id
        """
        )

    def _group_by(self):
        return (
            super()._group_by()
            + """ ,
            rp.zip,
            rp.city,
            rp.street,
            rp.street2,
            rp.country_id,
            rp.state_id
        """
        )

    def _from(self):
        return (
            super()._from()
            + """
                INNER JOIN project_project pp
                    ON pp.id = t.project_id
                    AND pp.is_fsm = 'true'
                LEFT JOIN res_partner rp
                    ON rp.id = t.partner_id
        """
        )

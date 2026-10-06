from odoo import fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.tools import frozendict

from odoo.addons.helpdesk.models.helpdesk_ticket import TICKET_PRIORITY
from odoo.addons.rating.models.rating_data import RATING_LIMIT_MIN


class HelpdeskTicketReportAnalysis(models.Model):
    _name = "helpdesk.ticket.report.analysis"
    _description = "Ticket Analysis"
    _auto = False
    _depends = frozendict(
        {
            "helpdesk.ticket": [
                "active",
                "assign_date",
                "assign_hours",
                "avg_response_hours",
                "close_date",
                "close_hours",
                "create_date",
                "description",
                "first_response_hours",
                "kanban_state",
                "name",
                "partner_email",
                "partner_id",
                "partner_name",
                "priority",
                "rating_last_value",
                "sla_deadline",
                "sla_deadline_hours",
                "stage_id",
                "team_id",
                "ticket_ref",
                "user_id",
                "phone_ids",
            ],
            "phone.number": ["number", "primary", "sequence"],
            "rating.rating": ["consumed", "rating", "res_id", "res_model"],
            "team.team": ["company_id", "helpdesk_use_rating"],
        }
    )
    _order = "create_date DESC"

    ticket_id = fields.Many2one(
        comodel_name="helpdesk.ticket",
        readonly=True,
    )
    description = fields.Text(readonly=True)
    tag_ids = fields.Many2many(
        comodel_name="helpdesk.tag",
        relation="helpdesk_tag_helpdesk_ticket_rel",
        column1="helpdesk_ticket_id",
        column2="helpdesk_tag_id",
        string="Tags",
        readonly=True,
    )
    ticket_ref = fields.Char(
        string="Ticket IDs Sequence",
        readonly=True,
    )
    name = fields.Char(
        string="Subject",
        readonly=True,
    )
    sla_fail = fields.Boolean(
        related="ticket_id.sla_fail",
        readonly=True,
    )
    sla_success = fields.Boolean(
        string="SLA Status Success",
        readonly=True,
        aggregator="bool_or",
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
    create_date = fields.Datetime(
        string="Ticket Creation Date",
        readonly=True,
    )
    priority = fields.Selection(
        selection=TICKET_PRIORITY,
        string="Minimum Priority",
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Assigned To",
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        readonly=True,
    )
    partner_name = fields.Char(
        string="Customer Name",
        readonly=True,
    )
    partner_email = fields.Char(
        string="Customer Email",
        readonly=True,
    )
    partner_phone = fields.Char(
        string="Customer Phone",
        readonly=True,
    )
    stage_id = fields.Many2one(
        comodel_name="helpdesk.stage",
        readonly=True,
    )
    sla_deadline = fields.Datetime(
        string="Ticket Deadline",
        readonly=True,
    )
    ticket_deadline_hours = fields.Float(
        string="Working Hours until SLA Deadline",
        readonly=True,
        aggregator="avg",
    )
    ticket_close_hours = fields.Float(
        string="Working Hours to Close",
        readonly=True,
        aggregator="avg",
    )
    ticket_open_hours = fields.Float(
        string="Hours Open",
        readonly=True,
        aggregator="avg",
    )
    ticket_assignation_hours = fields.Float(
        string="Working Hours to Assign",
        readonly=True,
        aggregator="avg",
    )
    close_date = fields.Datetime(
        string="Closing Date",
        readonly=True,
    )
    assign_date = fields.Datetime(
        string="First assignment date",
        readonly=True,
    )
    rating_last_value = fields.Float(
        string="Rating (1-5)",
        readonly=True,
        aggregator="avg",
    )
    active = fields.Boolean(readonly=True)
    team_id = fields.Many2one(
        comodel_name="team.team",
        string="Helpdesk Team",
        readonly=True,
        domain=[("use_helpdesk", "=", True)],
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    message_is_follower = fields.Boolean(
        related="ticket_id.message_is_follower",
        export_string_translation=False,
    )
    kanban_state = fields.Selection(
        selection=[("normal", "Grey"), ("done", "Green"), ("blocked", "Red")],
        readonly=True,
    )
    first_response_hours = fields.Float(
        string="Hours to First Response",
        readonly=True,
        aggregator="avg",
    )
    avg_response_hours = fields.Float(
        string="Average Hours to Respond",
        readonly=True,
        aggregator="avg",
    )
    rating_avg = fields.Float(
        string="Average Rating",
        readonly=True,
        aggregator="avg",
    )

    def _select(self):
        return """
            SELECT T.id AS id,
                   T.id AS ticket_id,
                   T.description,
                   T.ticket_ref AS ticket_ref,
                   T.name AS name,
                   T.create_date AS create_date,
                   T.priority AS priority,
                   T.user_id AS user_id,
                   T.partner_id AS partner_id,
                   T.partner_name AS partner_name,
                   T.partner_email AS partner_email,
                   (SELECT PN.number
                      FROM helpdesk_ticket_phone_number_rel REL
                      JOIN phone_number PN ON PN.id = REL.phone_number_id
                     WHERE REL.ticket_id = T.id
                     ORDER BY PN."primary" DESC, PN.sequence, PN.id
                     LIMIT 1) AS partner_phone,
                   T.stage_id AS stage_id,
                   T.sla_deadline AS sla_deadline,
                   NULLIF(T.sla_deadline_hours, 0) AS ticket_deadline_hours,
                   NULLIF(T.close_hours, 0) AS ticket_close_hours,
                   CASE
                     WHEN EXTRACT(EPOCH FROM (COALESCE(T.close_date, NOW() AT TIME ZONE 'UTC') - T.create_date)) / 3600 < 1 THEN NULL
                     ELSE EXTRACT(EPOCH FROM (COALESCE(T.close_date, NOW() AT TIME ZONE 'UTC') - T.create_date)) / 3600
                   END AS ticket_open_hours,
                   NULLIF(T.assign_hours, 0) AS ticket_assignation_hours,
                   T.close_date AS close_date,
                   T.assign_date AS assign_date,
                   CASE WHEN ht.helpdesk_use_rating AND COUNT(rt.id) > 0 THEN T.rating_last_value ELSE NULL END as rating_last_value,
                   CASE WHEN ht.helpdesk_use_rating AND COUNT(rt.id) > 0 THEN AVG(rt.rating) ELSE NULL END as rating_avg,
                   T.active AS active,
                   T.team_id AS team_id,
                   ht.company_id AS company_id,
                   T.kanban_state AS kanban_state,
                   NULLIF(T.first_response_hours, 0) AS first_response_hours,
                   NULLIF(T.avg_response_hours, 0) AS avg_response_hours,
                   CASE
                       WHEN (T.sla_deadline IS NOT NULL AND T.sla_deadline > NOW() AT TIME ZONE 'UTC') THEN TRUE ELSE FALSE
                   END AS sla_success
        """

    def _group_by(self):
        return """
                t.id,
                ht.id
        """

    def _from(self):
        return f"""
            helpdesk_ticket T
                LEFT JOIN rating_rating rt ON rt.res_id = t.id
                        AND rt.res_model = 'helpdesk.ticket'
                        AND rt.consumed = True
                        AND rt.rating >= {RATING_LIMIT_MIN}
                INNER JOIN team_team ht ON ht.id = t.team_id
        """

    def init(self) -> None:
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """CREATE or REPLACE VIEW %s as (
            %s
            FROM %s
            GROUP BY %s
            )"""
            % (self._table, self._select(), self._from(), self._group_by())
        )

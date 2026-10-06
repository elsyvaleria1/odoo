from odoo import fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.tools import frozendict

from odoo.addons.helpdesk.models.helpdesk_ticket import TICKET_PRIORITY
from odoo.addons.rating.models.rating_data import RATING_LIMIT_MIN


class HelpdeskSlaReportAnalysis(models.Model):
    _name = "helpdesk.sla.report.analysis"
    _description = "SLA Status Analysis"
    _auto = False
    _depends = frozendict(
        {
            "helpdesk.sla": ["stage_id"],
            "helpdesk.sla.status": [
                "deadline",
                "exceeded_hours",
                "reached_datetime",
                "sla_id",
                "ticket_id",
            ],
            "helpdesk.stage": ["fold"],
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
                "stage_id",
                "team_id",
                "ticket_ref",
                "user_id",
                "phone_ids",
            ],
            "phone.number": ["number", "primary", "sequence"],
            "rating.rating": ["consumed", "rating", "res_id", "res_model"],
            "res.users": ["company_id"],
            "team.team": ["company_id"],
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
    ticket_open_hours = fields.Float(
        string="Hours Open",
        readonly=True,
        aggregator="avg",
    )
    ticket_closed = fields.Boolean(readonly=True)
    ticket_close_hours = fields.Integer(
        string="Working Hours to Close",
        readonly=True,
        aggregator="avg",
    )
    ticket_assignation_hours = fields.Integer(
        string="Working Hours to Assign",
        readonly=True,
        aggregator="avg",
    )
    close_date = fields.Datetime(
        string="Closing Date",
        readonly=True,
    )
    sla_id = fields.Many2one(
        comodel_name="helpdesk.sla",
        string="SLA",
        readonly=True,
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
    sla_stage_id = fields.Many2one(
        comodel_name="helpdesk.stage",
        string="SLA Stage",
        readonly=True,
    )
    sla_deadline = fields.Datetime(
        string="SLA Deadline",
        readonly=True,
        aggregator="min",
    )
    sla_status = fields.Selection(
        selection=[
            ("failed", "SLA Failed"),
            ("reached", "SLA Success"),
            ("ongoing", "SLA in Progress"),
        ],
        string="Status",
        readonly=True,
    )
    sla_fail = fields.Boolean(
        string="SLA Status Failed",
        readonly=True,
        aggregator="bool_or",
    )
    sla_success = fields.Boolean(
        string="SLA Status Success",
        readonly=True,
        aggregator="bool_or",
    )
    sla_exceeded_hours = fields.Integer(
        string="Working Hours until SLA Deadline",
        readonly=True,
        aggregator="avg",
        help="Day to reach the stage of the SLA, without taking the working calendar into account",
    )
    sla_status_failed = fields.Integer(
        string="Number of SLAs Failed",
        readonly=True,
        aggregator="avg",
    )
    active = fields.Boolean(readonly=True)
    rating_last_value = fields.Float(
        string="Rating (1-5)",
        readonly=True,
        aggregator="avg",
    )
    rating_avg = fields.Float(
        string="Average Rating",
        readonly=True,
        aggregator="avg",
    )
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
    avg_response_hours = fields.Float(
        string="Average Hours to Respond",
        readonly=True,
        aggregator="avg",
    )
    first_response_hours = fields.Float(
        string="Hours to First Response",
        readonly=True,
        aggregator="avg",
    )

    def _select(self):
        return """
            SELECT DISTINCT T.id as id,
                            T.id AS ticket_id,
                            T.description,
                            T.ticket_ref AS ticket_ref,
                            T.name AS name,
                            T.create_date AS create_date,
                            T.team_id,
                            T.active AS active,
                            T.stage_id AS stage_id,
                            T.user_id,
                            T.partner_id,
                            T.partner_name AS partner_name,
                            T.partner_email AS partner_email,
                            (SELECT PN.number
                      FROM helpdesk_ticket_phone_number_rel REL
                      JOIN phone_number PN ON PN.id = REL.phone_number_id
                     WHERE REL.ticket_id = T.id
                     ORDER BY PN."primary" DESC, PN.sequence, PN.id
                     LIMIT 1) AS partner_phone,
                            TEAM.company_id,
                            T.kanban_state AS kanban_state,
                            NULLIF(T.rating_last_value, 0) AS rating_last_value,
                            AVG(rt.rating) as rating_avg,
                            T.priority AS priority,
                            NULLIF(T.close_hours, 0) AS ticket_close_hours,
                            CASE
                                WHEN EXTRACT(EPOCH FROM (COALESCE(T.assign_date, NOW() AT TIME ZONE 'UTC') - T.create_date)) / 3600 < 1 THEN NULL
                                ELSE EXTRACT(EPOCH FROM (COALESCE(T.assign_date, NOW() AT TIME ZONE 'UTC') - T.create_date)) / 3600
                            END AS ticket_open_hours,
                            NULLIF(T.assign_hours, 0) AS ticket_assignation_hours,
                            NULLIF(T.avg_response_hours, 0) AS avg_response_hours,
                            NULLIF(T.first_response_hours, 0) AS first_response_hours,
                            T.close_date AS close_date,
                            STAGE.fold AS ticket_closed,
                            SLA.stage_id as sla_stage_id,
                            SLA_S.deadline AS sla_deadline,
                            SLA.id as sla_id,
                            SLA_S.exceeded_hours AS sla_exceeded_hours,
                            SLA_S.reached_datetime >= SLA_S.deadline OR (SLA_S.reached_datetime IS NULL AND SLA_S.deadline < NOW() AT TIME ZONE 'UTC') AS sla_fail,
                            CASE
                                WHEN SLA_S.reached_datetime IS NOT NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.reached_datetime >= SLA_S.deadline THEN 1
                                WHEN SLA_S.reached_datetime IS NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.deadline < NOW() AT TIME ZONE 'UTC' THEN 1
                                ELSE NULL
                            END AS sla_status_failed,
                            CASE
                                WHEN SLA_S.reached_datetime IS NOT NULL AND (SLA_S.deadline IS NULL OR SLA_S.reached_datetime < SLA_S.deadline) THEN 'reached'
                                WHEN (SLA_S.reached_datetime IS NOT NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.reached_datetime >= SLA_S.deadline) OR
                                    (SLA_S.reached_datetime IS NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.deadline < NOW() AT TIME ZONE 'UTC') THEN 'failed'
                                WHEN SLA_S.reached_datetime IS NULL AND (SLA_S.deadline IS NULL OR SLA_S.deadline > NOW() AT TIME ZONE 'UTC') THEN 'ongoing'
                            END AS sla_status,
                            CASE
                                WHEN (SLA_S.deadline IS NOT NULL AND SLA_S.deadline > NOW() AT TIME ZONE 'UTC') THEN TRUE ELSE FALSE
                            END AS sla_success
        """

    def _group_by(self):
        return """
                t.id,
                TEAM.id,
                STAGE.fold,
                SLA.stage_id,
                SLA_S.deadline,
                SLA_S.reached_datetime,
                SLA.id,
                SLA_S.exceeded_hours
        """

    def _from(self):
        return f"""
            helpdesk_ticket T
            LEFT JOIN team_team TEAM ON TEAM.id = T.team_id
            LEFT JOIN rating_rating rt ON rt.res_id = t.id
                    AND rt.res_model = 'helpdesk.ticket'
                    AND rt.consumed = True
                    AND rt.rating >= {RATING_LIMIT_MIN}
            LEFT JOIN helpdesk_stage STAGE ON T.stage_id = STAGE.id
            RIGHT JOIN helpdesk_sla_status SLA_S ON T.id = SLA_S.ticket_id
            LEFT JOIN helpdesk_sla SLA ON SLA.id = SLA_S.sla_id
        """

    def _where(self):
        return """
            T.active = true
        """

    def _order_by(self) -> str:
        return """
            id, sla_stage_id
        """

    def init(self) -> None:
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """CREATE or REPLACE VIEW %s as (
            %s
            FROM %s
            WHERE %s
            GROUP BY %s
            ORDER BY %s
            )"""
            % (
                self._table,
                self._select(),
                self._from(),
                self._where(),
                self._group_by(),
                self._order_by(),
            )
        )

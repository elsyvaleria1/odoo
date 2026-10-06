from odoo import fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.tools import frozendict


class HrContractRecruitmentReport(models.Model):
    _name = "hr.contract.recruitment.report"
    _description = "Contract and Recruitment Analysis Report"
    _auto = False
    _depends = frozendict(
        {
            "hr.contract.salary.offer": [
                "applicant_id",
                "company_id",
                "create_date",
                "employee_job_id",
                "state",
            ],
        }
    )
    _rec_name = "offer_create_date"
    _order = "offer_create_date desc"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    offer_id = fields.Many2one(
        comodel_name="hr.contract.salary.offer",
        readonly=True,
    )
    applicant_id = fields.Many2one(
        comodel_name="hr.applicant",
        readonly=True,
    )
    job_id = fields.Many2one(
        comodel_name="hr.job",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    offer_state = fields.Selection(
        selection=[
            ("open", "In Progress"),
            ("half_signed", "Partially Signed"),
            ("full_signed", "Fully Signed"),
            ("expired", "Expired"),
            ("refused", "Refused"),
            ("cancelled", "Cancelled"),
        ],
        readonly=True,
    )
    offer_create_date = fields.Date(readonly=True)

    in_progress = fields.Integer(
        readonly=True,
        aggregator="sum",
    )
    fully_signed = fields.Integer(
        readonly=True,
        aggregator="sum",
    )
    partially_signed = fields.Integer(
        readonly=True,
        aggregator="sum",
    )
    refused = fields.Integer(
        readonly=True,
        aggregator="sum",
    )
    expired = fields.Integer(
        readonly=True,
        aggregator="sum",
    )
    cancelled = fields.Integer(
        readonly=True,
        aggregator="sum",
    )

    def action_view_applicant(self) -> dict | None:
        self.check_singleton()
        if not self.applicant_id:
            return None
        return {
            "name": self.env._("Applicants"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "hr.applicant",
            "res_id": self.applicant_id.id,
            "target": "current",
        }

    def _query(self, fields=""):
        return (
            """
            SELECT
            o.id as id,
            o.id as offer_id,
            o.state as offer_state,
            o.create_date as offer_create_date,
            o.employee_job_id as job_id,
            o.applicant_id as applicant_id,
            o.company_id as company_id,
            CASE WHEN o.state='open' THEN 1 ELSE 0 END as in_progress,
            CASE WHEN o.state='half_signed' THEN 1 ELSE 0 END as partially_signed,
            CASE WHEN o.state='full_signed' THEN 1 ELSE 0 END as fully_signed,
            CASE WHEN o.state='refused' THEN 1 ELSE 0 END as refused,
            CASE WHEN o.state='cancelled' THEN 1 ELSE 0 END as cancelled,
            CASE WHEN o.state='expired' THEN 1 ELSE 0 END as expired
            FROM hr_contract_salary_offer o
            %s
            """
            % fields
        )

    def init(self) -> None:
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """CREATE or REPLACE VIEW %s as (%s)""" % (self._table, self._query())
        )

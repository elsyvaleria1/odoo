from odoo import api, fields, models


class WizardPosSessionPrintSaleDetail(models.TransientModel):
    _inherit = "wizard.pos.session.print.sale.detail"

    add_report_per_employee = fields.Boolean(
        string="Add a report per each employee",
        default=True,
    )
    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        compute="_compute_employee_ids",
    )

    def _prepare_report_params(self) -> dict:
        return {
            **super()._prepare_report_params(),
            "employee_ids": self.employee_ids.ids
            if self.add_report_per_employee
            else [],
        }

    @api.depends("pos_session_id")
    def _compute_employee_ids(self) -> None:
        for wizard in self:
            domain = [("session_id", "=", wizard.pos_session_id.id)]
            orders = self.env["pos.order"].search(domain)  # noqa: E8507 -- a transient wizard: one record
            wizard.employee_ids = orders.mapped("employee_id")

    @api.onchange("pos_session_id")
    def _onchange_pos_session_id(self) -> None:
        self.check_singleton()
        if self.pos_session_id and not self.employee_ids:
            self.add_report_per_employee = False

from odoo import api, fields, models


class HrAttendanceOvertimeRule(models.Model):
    _name = "hr.attendance.overtime.rule"
    _inherit = "hr.attendance.overtime.rule"

    @api.model
    def _get_default_work_entry_type_id(self):
        return self.env["hr.work.entry.type"].browse(
            self.env["hr.version"]._get_default_work_entry_type_overtime_id()
        )

    work_entry_type_id = fields.Many2one(
        comodel_name="hr.work.entry.type",
        default=lambda self: self._get_default_work_entry_type_id(),
        required=True,
    )
    amount_rate = fields.Float(
        string="Salary Rate",
        compute="_compute_amount_rate",
        default=None,
        store=True,
        readonly=False,
    )

    _if_paid_work_entry_type_defined = models.Constraint(
        "CHECK(NOT paid OR work_entry_type_id IS NOT NULL)",
        "if paid the work entry should be defined",
    )

    @api.depends("work_entry_type_id")
    def _compute_amount_rate(self) -> None:
        for rule in self:
            rule.amount_rate = rule.work_entry_type_id.amount_rate

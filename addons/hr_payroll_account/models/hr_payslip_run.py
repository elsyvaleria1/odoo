from odoo import fields, models
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    move_id = fields.Many2one(
        comodel_name="account.move",
        readonly=True,
    )
    move_state = fields.Selection(
        related="move_id.state",
        string="Move State",
    )

    def action_view_move(self) -> dict:
        self.check_singleton()
        if not self.move_id:
            raise UserError(self.env._("This pay run has no journal entry to display."))
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Journal Entry"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.move_id.id,
        }

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
        # Same two holes as the payslip button: `self.move_id.id` raises a bare
        # `Expected singleton` on a selection, and `False` opened a blank
        # `account.move` form. Kept as its own method rather than shared with
        # `hr.payslip`: the two models have no common base, and a mixin for
        # eight lines would buy coupling, not clarity.
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

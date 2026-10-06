from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    payslip_ids = fields.One2many(
        comodel_name="hr.payslip",
        inverse_name="move_id",
        string="Payslips",
        copy=False,
        readonly=True,
    )
    payslip_count = fields.Count(
        count_of="payslip_ids",
        string="# of Payslips",
        compute_sudo=True,
        readonly=True,
    )

    def action_view_payslip(self):
        self.check_singleton()
        return_action = {
            "name": "Payslips",
            "type": "ir.actions.act_window",
            "res_model": "hr.payslip",
        }
        if self.payslip_count > 1:
            return_action.update(
                {
                    "view_mode": "list,form",
                    "domain": [("id", "in", self.payslip_ids.ids)],
                }
            )
        else:
            return_action.update(
                {
                    "view_mode": "form",
                    "res_id": self.payslip_ids.id,
                }
            )

        return return_action

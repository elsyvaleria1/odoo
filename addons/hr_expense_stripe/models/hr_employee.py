from odoo import fields, models


class HrEmployee(models.Model):
    _name = "hr.employee"
    _inherit = ["hr.employee"]

    private_stripe_id = fields.Char(
        string="Stripe ID",
        index="btree",
        copy=False,
        readonly=True,
        classification="hr.private",
    )

    def action_archive(self):
        self.check_access("write")
        archived_employees = self.filtered("active")
        archived_employees.sudo().user_id.stripe_card_ids.filtered(
            "stripe_id"
        ).action_pause_card()
        return super().action_archive()

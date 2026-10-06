from odoo import Command, fields, models


class WizardSaleCommissionPlanAddUser(models.TransientModel):
    _name = "wizard.sale.commission.plan.add.user"
    _description = "Wizard for selecting multiple users"

    user_ids = fields.Many2many(
        comodel_name="res.users",
        string="Salespersons",
        domain="[('share', '=', False)]",
    )

    def submit(self):
        plan_id = self.env["sale.commission.plan"].browse(
            self.env.context.get("active_ids")
        )
        plan_id.user_ids = [
            Command.create({"user_id": user_id.id, "plan_id": plan_id.id})
            for user_id in self.user_ids
        ]

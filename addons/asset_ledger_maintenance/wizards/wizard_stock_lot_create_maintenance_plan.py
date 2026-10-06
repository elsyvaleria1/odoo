from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class WizardStockLotCreateMaintenancePlan(models.TransientModel):
    _name = "wizard.stock.lot.create.maintenance.plan"
    _description = "Generate Maintenance Plans"

    template_id = fields.Many2one(
        comodel_name="maintenance.plan.template",
        required=True,
        help="Maintenance plan template to apply to selected equipment",
    )
    equipment_ids = fields.Many2many(
        comodel_name="product.trace",
        required=True,
        help="Equipment to create maintenance plans for (pre-filled from selection)",
    )
    equipment_count = fields.Count(count_of="equipment_ids")
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)

        equipment_ids = self.env.context.get("active_ids", [])

        if not equipment_ids:
            raise UserError(
                self.env._(
                    "No equipment selected. Please select equipment from the list before creating maintenance plans."
                )
            )

        equipments = self.env["product.trace"].browse(equipment_ids)
        non_maintenance = equipments.filtered(lambda e: not e.maintenance_ok)

        if non_maintenance:
            raise UserError(
                self.env._(
                    "The following equipment does not have recurring maintenance enabled:\n\n"
                    "%(equipment)s\n\n"
                    "Please enable recurring maintenance before creating plans.",
                    equipment=", ".join(non_maintenance.mapped("name")),
                )
            )

        res["equipment_ids"] = [Command.set(equipment_ids)]
        return res

    def action_apply_template(self):
        self.check_singleton()

        if not self.equipment_ids:
            raise UserError(self.env._("Please select at least one equipment."))

        if not self.template_id:
            raise UserError(self.env._("Please select a maintenance template."))

        created_plans = self.template_id.create_plans_for_equipment(
            self.equipment_ids.ids
        )

        if not created_plans:
            raise UserError(
                self.env._(
                    "No maintenance plans were created. "
                    "Plans may already exist for the selected equipment with this template."
                )
            )

        return {
            "type": "ir.actions.act_window",
            "name": "Generated Maintenance Plans",
            "res_model": "maintenance.plan",
            "view_mode": "list,form",
            "domain": [("id", "in", created_plans.ids)],
            "target": "current",
        }

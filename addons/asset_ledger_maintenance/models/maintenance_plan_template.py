from odoo import fields, models
from odoo.exceptions import ValidationError


class MaintenancePlanTemplate(models.Model):
    _name = "maintenance.plan.template"
    _description = "Maintenance Plan Template"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity", "mixin.recurrence.interval"]

    name = fields.Char(
        required=True,
        tracking=True,
    )
    active = fields.Boolean(
        default=True,
        tracking=True,
    )
    repeat_interval = fields.Integer(required=True)
    repeat_unit = fields.Selection(
        default="month",
        required=True,
    )
    duration = fields.Float(
        default=lambda self: float(
            self.env.registry.settings.get(
                self.env, "asset_ledger_maintenance.default_duration", "1.0"
            )
        )
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        tracking=True,
    )
    asset_kind_id = fields.Many2one(
        comodel_name="resource.kind",
        tracking=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        domain="[('asset_kind_id', '=', asset_kind_id)]",
        tracking=True,
    )
    instructions = fields.Html()
    equipment_category_ids = fields.Many2many(comodel_name="product.category")
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    maintenance_plan_ids = fields.One2many(
        comodel_name="maintenance.plan",
        inverse_name="template_id",
    )
    maintenance_plan_count = fields.Count(count_of="maintenance_plan_ids")

    def action_view_maintenance_plans(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": "Generated Maintenance Plans",
            "res_model": "maintenance.plan",
            "view_mode": "list,form",
            "domain": [("template_id", "=", self.id)],
            "context": {"default_template_id": self.id},
        }

    def create_plans_for_equipment(self, equipment_ids):
        plans = self.env["maintenance.plan"]

        for template in self:
            equipments = self.env["product.trace"].browse(equipment_ids)

            incompatible_equipments = []

            for equipment in equipments:
                if not equipment.maintenance_ok:
                    incompatible_equipments.append(
                        {
                            "equipment": equipment,
                            "reason": "does not have recurring maintenance enabled",
                        }
                    )
                    continue

                if template.product_id:
                    if equipment.product_id != template.product_id:
                        product_reason = (
                            f"has product '{equipment.product_id.display_name}' "
                            f"but template requires '{template.product_id.display_name}'"
                        )
                        incompatible_equipments.append(
                            {
                                "equipment": equipment,
                                "reason": product_reason,
                            }
                        )
                        continue

                elif template.asset_kind_id:
                    if equipment.kind_id != template.asset_kind_id:
                        equipment_type_label = equipment.kind_id.display_name or "None"
                        template_type_label = template.asset_kind_id.display_name
                        asset_reason = f"has asset kind '{equipment_type_label}' but template requires '{template_type_label}'"
                        incompatible_equipments.append(
                            {
                                "equipment": equipment,
                                "reason": asset_reason,
                            }
                        )
                        continue

                existing_plan = plans.search(
                    [
                        ("asset_id", "=", equipment.asset_id.id),
                        ("template_id", "=", template.id),
                        ("active", "=", True),
                    ],
                    limit=1,
                )

                if existing_plan:
                    continue

                vals = {
                    "asset_id": equipment.asset_id.id,
                    "repeat_interval": template.repeat_interval,
                    "repeat_unit": template.repeat_unit,
                    "repeat_anchor": "completion",
                    "date_first_occurrence": fields.Datetime.now()
                    + template._get_recurrence_delta(),
                    "duration": template.duration,
                    "user_id": template.user_id.id,
                    "description": template.instructions,
                    "template_id": template.id,
                    "company_id": (template.company_id or self.env.company).id,
                }

                plan = plans.create(vals)
                plans |= plan

            if incompatible_equipments:
                error_lines = [
                    f"  - {item['equipment'].name}: {item['reason']}"
                    for item in incompatible_equipments
                ]

                raise ValidationError(
                    self.env._(
                        "Cannot apply template '%(template)s' to %(count)d equipment(s):\n\n"
                        "%(errors)s\n\n"
                        "Template requirements:\n"
                        "  • Product: %(product)s\n"
                        "  • Asset Kind: %(asset_kind)s\n"
                        "  • Recurring Maintenance: Required",
                        template=template.name,
                        count=len(incompatible_equipments),
                        errors="\n".join(error_lines),
                        product=(
                            template.product_id.display_name
                            if template.product_id
                            else "Any"
                        ),
                        asset_kind=template.asset_kind_id.display_name or "Any",
                    )
                )

        return plans

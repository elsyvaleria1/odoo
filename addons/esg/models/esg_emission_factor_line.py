from collections import defaultdict

from odoo import api, fields, models


class EsgEmissionFactorLine(models.Model):
    _name = "esg.emission.factor.line"
    _description = "Emission Factor Line"
    _inherit = ["mixin.mail.thread"]

    esg_emission_factor_id = fields.Many2one(
        comodel_name="esg.emission.factor",
        string="Emission Factor",
        index=True,
    )
    activity_type_id = fields.Many2one(
        comodel_name="esg.activity.type",
        tracking=True,
    )
    gas_id = fields.Many2one(
        comodel_name="esg.gas",
        required=True,
        tracking=True,
    )
    quantity = fields.Float(
        string="kg",
        digits=(16, 8),
        default=1.0,
        required=True,
        tracking=True,
    )
    esg_emissions_value = fields.Float(
        string="Emissions (kgCO₂e)",
        compute="_compute_esg_emissions_value",
        store=True,
        tracking=True,
    )

    @api.depends("quantity", "gas_id.global_warming_potential")
    def _compute_esg_emissions_value(self) -> None:
        for emission in self:
            emission.esg_emissions_value = (
                emission.quantity * emission.gas_id.global_warming_potential
            )

    @api.depends("gas_id")
    def _compute_display_name(self):
        for gas_line in self:
            gas_line.display_name = self.env._(
                "%(gas_name)s (%(quantity)s kg)",
                gas_name=gas_line.gas_id.name,
                quantity=gas_line.quantity,
            )

    def write(self, vals):
        tracked_field_names = {
            fname for fname in self._track_get_fields() if fname in vals
        }
        tracked_fields = self.fields_get(tracked_field_names)

        gas_line_initial_values = defaultdict(dict)
        for gas_line in self:
            for fname in tracked_field_names:
                gas_line_initial_values[gas_line][fname] = gas_line[fname]
            gas_line_initial_values[gas_line].update(
                {
                    "gas_name": gas_line.gas_id.name,
                    "activity_type_name": gas_line.activity_type_id.name,
                }
            )

        res = super().write(vals)

        for gas_line, initial_values in gas_line_initial_values.items():
            tracking_value_ids = gas_line._mail_track(tracked_fields, initial_values)[1]
            if tracking_value_ids:
                gas_line.esg_emission_factor_id._message_log(
                    body=self.env._(
                        "Updated values for %(gas_name)s (%(activity_type_name)s)",
                        gas_name=initial_values["gas_name"],
                        activity_type_name=initial_values["activity_type_name"],
                    ),
                    tracking_value_ids=tracking_value_ids,
                )

        return res

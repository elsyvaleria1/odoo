from odoo import api, fields, models
from odoo.tools import frozendict


class EsgOtherEmission(models.Model):
    _name = "esg.other.emission"
    _description = "Other Emission"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=True),
        }
    )

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    date = fields.Date(required=True)
    date_end = fields.Date()
    esg_emission_factor_id = fields.Many2one(
        comodel_name="esg.emission.factor",
        string="Emission Factor",
        index="btree_not_null",
        required=True,
    )
    note = fields.Text()
    quantity = fields.Integer(
        default=1,
        required=True,
    )
    esg_emissions_value = fields.Float(
        string="Emissions (kgCO₂e)",
        compute="_compute_esg_emissions_value",
    )
    esg_uncertainty_absolute_value = fields.Float(
        string="Uncertainty (kgCO₂e)",
        compute="_compute_esg_uncertainty_absolute_value",
    )
    esg_uncertainty_value = fields.Float(
        related="esg_emission_factor_id.esg_uncertainty_value"
    )
    uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit of Measure",
        compute="_compute_uom_id",
        store=True,
        readonly=False,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
        store=True,
        readonly=False,
    )
    compute_method = fields.Selection(related="esg_emission_factor_id.compute_method")
    esg_emission_multiplicator = fields.Float(
        export_string_translation=False,
        compute="_compute_esg_emission_multiplicator",
        store=True,
    )  # Technical field, storing the multiplicator to apply to the gas volumes (important for the report)

    @api.depends(
        "quantity",
        "compute_method",
        "esg_emission_factor_id.currency_id",
        "esg_emission_factor_id.uom_id",
        "uom_id",
        "currency_id",
    )
    def _compute_esg_emission_multiplicator(self) -> None:
        for emission in self:
            if emission.compute_method == "monetary":
                if emission.currency_id and emission.esg_emission_factor_id.currency_id:
                    emission.esg_emission_multiplicator = (
                        emission.esg_emission_factor_id.currency_id._convert(
                            emission.quantity, emission.currency_id
                        )
                    )
                else:
                    emission.esg_emission_multiplicator = 0
            elif emission.uom_id and emission.esg_emission_factor_id.uom_id:
                emission.esg_emission_multiplicator = (
                    emission.esg_emission_factor_id.uom_id._get_quantity_in_unit(
                        emission.quantity, emission.uom_id
                    )
                )
            else:
                emission.esg_emission_multiplicator = 0

    @api.depends(
        "esg_emission_multiplicator", "esg_emission_factor_id.esg_emissions_value"
    )
    def _compute_esg_emissions_value(self) -> None:
        for emission in self:
            emission.esg_emissions_value = (
                emission.esg_emission_factor_id.esg_emissions_value
                * emission.esg_emission_multiplicator
            )

    @api.depends("esg_emissions_value", "esg_uncertainty_value")
    def _compute_esg_uncertainty_absolute_value(self) -> None:
        for emission in self:
            emission.esg_uncertainty_absolute_value = (
                emission.esg_emissions_value * emission.esg_uncertainty_value
            )

    @api.depends("compute_method", "esg_emission_factor_id")
    def _compute_uom_id(self) -> None:
        for emission in self:
            if emission.compute_method == "monetary":
                emission.uom_id = False
            else:
                emission.uom_id = emission.esg_emission_factor_id.uom_id

    @api.depends("compute_method", "esg_emission_factor_id")
    def _compute_currency_id(self) -> None:
        for emission in self:
            if emission.compute_method == "physically":
                emission.currency_id = False
            else:
                emission.currency_id = emission.esg_emission_factor_id.currency_id

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [
            dict(vals, name=self.env._("%s (copy)", emission.name))
            for emission, vals in zip(self, vals_list, strict=False)
        ]

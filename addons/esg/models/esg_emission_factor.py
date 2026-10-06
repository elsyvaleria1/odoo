from odoo import api, fields, models


class EsgEmissionFactor(models.Model):
    _name = "esg.emission.factor"
    _description = "Emission Factor"
    _inherit = [
        "mixin.mail.thread",
    ]

    name = fields.Char(required=True)
    sequence = fields.Integer()
    active = fields.Boolean(default=True)

    code = fields.Char(index=True)  # required=True

    esg_emissions_value = fields.Float(
        string="Emissions (kgCO₂e)",
        compute="_compute_esg_emissions_value",
        store=True,
        readonly=False,
        tracking=True,
    )
    source_id = fields.Many2one(
        comodel_name="esg.emission.source",
        required=True,
    )
    scope = fields.Selection(related="source_id.scope")
    scope_complete_name = fields.Char(related="source_id.complete_name")
    company_id = fields.Many2one(comodel_name="res.company")

    valid_from = fields.Date()
    valid_to = fields.Date()

    esg_uncertainty_value = fields.Float(string="Uncertainty (%)")
    compute_method = fields.Selection(
        selection=[
            ("physically", "Physically (Quantity)"),
            ("monetary", "Monetary"),
        ],
        default="physically",
        required=True,
    )
    unit_name = fields.Char(compute="_compute_unit_name")
    database_id = fields.Many2one(comodel_name="esg.database")
    gas_line_ids = fields.One2many(
        comodel_name="esg.emission.factor.line",
        inverse_name="esg_emission_factor_id",
        tracking=True,
    )
    assignation_line_ids = fields.One2many(
        comodel_name="esg.assignation.line",
        inverse_name="esg_emission_factor_id",
    )
    description = fields.Html()
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
    activity_type_ids = fields.Many2many(
        comodel_name="esg.activity.type",
        string="Activity Types",
        compute="_compute_activity_type_ids",
        store=True,
    )
    account_move_line_ids = fields.One2many(
        comodel_name="account.move.line",
        inverse_name="esg_emission_factor_id",
    )
    esg_other_emission_ids = fields.One2many(
        comodel_name="esg.other.emission",
        inverse_name="esg_emission_factor_id",
    )
    nb_linked_emissions = fields.Integer(compute="_compute_nb_linked_emissions")
    region = fields.Char(string="Region / Regional Conditions")

    @api.depends("uom_id", "currency_id", "compute_method")
    def _compute_unit_name(self) -> None:
        for factor in self:
            if factor.compute_method == "monetary":
                factor.unit_name = factor.currency_id.name
            else:
                factor.unit_name = factor.uom_id.name

    @api.depends("gas_line_ids.esg_emissions_value")
    def _compute_esg_emissions_value(self) -> None:
        for factor in self:
            factor.esg_emissions_value = sum(
                factor.gas_line_ids.mapped("esg_emissions_value")
            )

    @api.depends("compute_method")
    def _compute_uom_id(self) -> None:
        for factor in self:
            if factor.compute_method == "monetary":
                factor.uom_id = False

    @api.depends("compute_method")
    def _compute_currency_id(self) -> None:
        for factor in self:
            if factor.compute_method == "physically":
                factor.currency_id = False

    @api.depends("gas_line_ids.activity_type_id")
    def _compute_activity_type_ids(self) -> None:
        for factor in self:
            factor.activity_type_ids = factor.gas_line_ids.activity_type_id

    @api.depends("account_move_line_ids", "esg_other_emission_ids")
    def _compute_nb_linked_emissions(self) -> None:
        for factor in self:
            factor.nb_linked_emissions = len(
                factor.account_move_line_ids.filtered(
                    lambda aml: aml.parent_state == "posted"
                ),
            ) + len(factor.esg_other_emission_ids)

    def action_view_linked_emissions(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._(
                "Emissions using %(emission_factor)s", emission_factor=self.name
            ),
            "type": "ir.actions.act_window",
            "view_mode": "list,kanban,graph,pivot",
            "res_model": "esg.carbon.emission.report",
            "domain": [("esg_emission_factor_id", "=", self.id)],
        }

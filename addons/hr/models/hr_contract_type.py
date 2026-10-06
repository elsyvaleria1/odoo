from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrContractType(models.Model):
    _name = "hr.contract.type"
    _description = "Contract Type"
    _order = "sequence"

    name = fields.Char(
        translate=True,
        required=True,
    )
    code = fields.Char(
        compute="_compute_code",
        store=True,
        readonly=False,
    )
    sequence = fields.Integer()
    country_id = fields.Many2one(
        comodel_name="res.country",
        domain=lambda self: [("id", "in", self.env.companies.country_id.ids)],
    )

    @api.depends("name")
    def _compute_code(self) -> None:
        for contract_type in self:
            if contract_type.code:
                continue
            _debug.logic(
                "code_defaults_to_name",
                contract_type=contract_type.id,
                name=contract_type.name,
            )
            contract_type.code = contract_type.name

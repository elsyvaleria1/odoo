from odoo import fields, models


class HrContractType(models.Model):
    _inherit = "hr.contract.type"

    monster_id = fields.Integer(
        string="Monster ID",
        help="Monster ID of the contract type.",
    )

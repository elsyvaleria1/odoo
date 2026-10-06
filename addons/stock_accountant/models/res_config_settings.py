from odoo import fields, models
from odoo.libs.debug_log import DebugLog

ACCOUNT_DOMAIN = [
    (
        "account_type",
        "not in",
        (
            "asset_receivable",
            "liability_payable",
            "asset_cash",
            "liability_credit_card",
            "off_balance",
        ),
    )
]


_debug = DebugLog(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    valuation_method = fields.Selection(
        related="company_id.stock_config_id.inventory_valuation",
        string="Inventory Valuation",
        readonly=False,
        required=True,
    )
    cost_method = fields.Selection(
        related="company_id.stock_config_id.cost_method",
        string="Inventory Cost Method",
        readonly=False,
        required=True,
    )
    inventory_period = fields.Selection(
        related="company_id.stock_config_id.inventory_period",
        string="Inventory Period",
        readonly=False,
        required=True,
    )
    stock_journal = fields.Many2one(
        comodel_name="account.journal",
        related="company_id.stock_config_id.account_stock_journal_id",
        string="Stock Journal",
        readonly=False,
    )
    stock_valuation_account_id = fields.Many2one(
        comodel_name="account.account",
        related="company_id.stock_config_id.account_stock_valuation_id",
        string="Stock Valuation Account",
        readonly=False,
    )

    def action_stock_open_valued_locations(self):
        _debug.lifecycle("valued_locations_open", settings=self)
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "stock.action_prod_inv_location_form"
        )
        action["context"] = {
            "search_default_inventory": 1,
            "search_default_prod_inv_location": 1,
        }
        return action

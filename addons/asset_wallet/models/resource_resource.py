from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    wallet_card_ids = fields.One2many(
        comodel_name="wallet.card",
        inverse_name="asset_id",
        string="Wallet Cards",
        groups="wallet.group_wallet_user",
    )
    count_wallet_card = fields.Count(
        count_of="wallet_card_ids",
        groups="wallet.group_wallet_user",
    )
    fuel_wallet_card_id = fields.Many2one(
        comodel_name="wallet.card",
        compute="_compute_card_summary",
        groups="wallet.group_wallet_user",
    )
    toll_wallet_card_id = fields.Many2one(
        comodel_name="wallet.card",
        compute="_compute_card_summary",
        groups="wallet.group_wallet_user",
    )
    has_fuel_wallet_card = fields.Boolean(compute="_compute_card_summary")
    has_toll_wallet_card = fields.Boolean(compute="_compute_card_summary")
    fuel_card_budget = fields.Monetary(
        compute="_compute_card_summary",
    )
    fuel_card_balance = fields.Monetary(
        compute="_compute_card_summary",
    )
    fuel_card_balance_to_reload = fields.Monetary(
        string="Fuel Card Amount to Reload",
        compute="_compute_card_summary",
    )
    highway_pass_budget = fields.Monetary(
        string="Toll Card Budget",
        compute="_compute_card_summary",
    )
    highway_pass_balance = fields.Monetary(
        string="Toll Card Balance",
        compute="_compute_card_summary",
    )
    highway_pass_balance_to_reload = fields.Monetary(
        string="Toll Card Amount to Reload",
        compute="_compute_card_summary",
    )

    @api.depends(
        "wallet_card_ids.kind",
        "wallet_card_ids.active",
        "wallet_card_ids.amount_balance",
        "wallet_card_ids.reorder_rule_id.amount_max",
        "wallet_card_ids.reorder_rule_id.amount_to_reload",
    )
    @_debug.perf.timed
    def _compute_card_summary(self) -> None:
        for asset in self:
            cards = asset.sudo().wallet_card_ids
            fuel = cards.filtered(lambda c: c.kind == "fuel")[:1]
            toll = cards.filtered(lambda c: c.kind == "toll")[:1]
            asset.fuel_wallet_card_id = fuel
            asset.toll_wallet_card_id = toll
            asset.has_fuel_wallet_card = bool(fuel)
            asset.has_toll_wallet_card = bool(toll)
            asset.fuel_card_budget = fuel.reorder_rule_id.amount_max
            asset.fuel_card_balance = fuel.amount_balance
            asset.fuel_card_balance_to_reload = fuel.reorder_rule_id.amount_to_reload
            asset.highway_pass_budget = toll.reorder_rule_id.amount_max
            asset.highway_pass_balance = toll.amount_balance
            asset.highway_pass_balance_to_reload = toll.reorder_rule_id.amount_to_reload

    def action_view_wallet_cards(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Wallet Cards"),
            "res_model": "wallet.card",
            "view_mode": "list,form",
            "domain": [("asset_id", "=", self.id)],
            "context": {"default_asset_id": self.id},
        }

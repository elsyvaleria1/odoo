from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    landed_cost_adjustment_line_ids = fields.One2many(
        comodel_name="stock.valuation.adjustment.lines",
        inverse_name="move_id",
    )

    def _get_value_from_extra(self, quantity, at_date=None):
        self.check_singleton()
        accounting_data = super()._get_value_from_extra(quantity, at_date=at_date)
        lcs = self._get_landed_cost_lines(at_date=at_date)
        if not lcs:
            return accounting_data
        lcs_desc = []
        for lc in lcs:
            accounting_data["value"] += lc.additional_landed_cost
            landed_cost = lc.cost_id
            value = lc.additional_landed_cost
            vendor_bill = landed_cost.vendor_bill_id
            if vendor_bill:
                desc = self.env._(
                    "+ %(value)s from %(vendor_bill)s (Landed Cost: %(landed_cost)s)",
                    value=self.company_currency_id.format(value),
                    vendor_bill=vendor_bill.display_name,
                    landed_cost=landed_cost.display_name,
                )
            else:
                desc = self.env._(
                    "+ %(value)s (Landed Cost: %(landed_cost)s)",
                    value=self.company_currency_id.format(value),
                    landed_cost=landed_cost.display_name,
                )
            lcs_desc.append(desc)
        description = self.env._(
            "Additional landed costs:\n%(landed_cost)s", landed_cost="\n".join(lcs_desc)
        )
        if not accounting_data["description"]:
            accounting_data["description"] = description
        else:
            accounting_data["description"] += "\n" + description
        return accounting_data

    def _get_landed_cost_lines(self, at_date=None):
        # through the one2many, so valuing a batch of moves one by one reads
        # every move's adjustment lines in one query
        self.check_singleton()
        at_date = at_date and fields.Date.to_date(at_date)
        lines = self.landed_cost_adjustment_line_ids.filtered(
            lambda line: (
                line.cost_id.state == "done"
                and (not at_date or line.cost_id.date <= at_date)
            )
        )
        _debug.logic("move_landed_cost_read", move=self, at_date=at_date, lines=lines)
        return lines

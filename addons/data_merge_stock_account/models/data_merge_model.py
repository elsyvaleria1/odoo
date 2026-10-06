from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class Data_MergeModel(models.Model):
    _inherit = "data_merge.model"

    @api.onchange("res_model_id")
    def _onchange_res_model_id(self) -> dict | None:
        _debug.logic("data_merge_stock_model_change", models=self)
        super()._onchange_res_model_id()

        if self.res_model_id.model in ("product.product", "product.template"):
            return {
                "warning": {
                    "title": self.env._("Warning"),
                    "message": self.env._(
                        "Merging some products is an important change that will impact your inventory valuation. "
                        "You may have to manually rectify it once done."
                    ),
                }
            }
        return None

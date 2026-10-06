from odoo import api, models


class IrQweb(models.AbstractModel):
    _inherit = "ir.qweb"

    @api.model
    def _get_eval_free_script_bundles(self) -> set[str]:
        return super()._get_eval_free_script_bundles() | {
            "im_livechat.assets_embed_external",
            "im_livechat.assets_livechat_support_tours",
        }

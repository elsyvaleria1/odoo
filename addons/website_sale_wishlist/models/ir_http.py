from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _frontend_pre_dispatch(cls) -> None:
        super()._frontend_pre_dispatch()
        request.wishlist = request.env["product.wishlist"]._lazy_current_wishlist()

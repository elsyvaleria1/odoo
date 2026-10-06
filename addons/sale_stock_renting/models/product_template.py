from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Padding Time

    preparation_time = fields.Float(
        string="Reserve product",
        company_dependent=True,
        help="Temporarily make this product unavailable before pickup.",
    )

    @api.constrains("rent_ok", "tracking")
    def _check_rental_tracking(self) -> None:
        for template in self:
            if template.rent_ok and template.tracking == "lot":
                _debug.logic("rental_lot_tracking_refused", templates=self)
                raise ValidationError(
                    self.env._(
                        "Tracking by lots isn't supported for rental products."
                        "\nYou should rather change the tracking mode to unique serial numbers."
                    )
                )

    def _compute_show_qty_status_button(self) -> None:
        super()._compute_show_qty_status_button()
        for template in self:
            if template.rent_ok and not template.sale_ok:
                template.show_forecasted_qty_status_button = False

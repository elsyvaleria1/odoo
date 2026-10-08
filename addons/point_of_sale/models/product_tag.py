from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import is_html_empty

_debug = DebugLog(__name__)


class ProductTag(models.Model):
    _name = "product.tag"
    _inherit = ["product.tag", "mixin.pos.load"]

    pos_description = fields.Html(
        string="Description",
        translate=True,
    )
    has_image = fields.Boolean(compute="_compute_has_image")

    @api.model
    def _load_pos_data_fields(self, config):
        return ["name", "pos_description", "color", "has_image", "write_date"]

    @api.depends("image")
    def _compute_has_image(self) -> None:
        for record in self:
            record.has_image = bool(record.image)

    def write(self, vals):
        if vals.get("pos_description") and is_html_empty(vals["pos_description"]):
            _debug.logic("empty_pos_description_cleared", tags=self)
            vals["pos_description"] = ""
        return super().write(vals)

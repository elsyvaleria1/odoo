from urllib.parse import urlencode

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "mixin.website.published.multi"]

    visitor_ids = fields.One2many(
        comodel_name="website.visitor",
        inverse_name="partner_id",
        string="Visitors",
    )

    def google_map_link(self, zoom=10):
        params = {
            "q": "%s, %s %s, %s"
            % (
                self.street or "",
                self.city or "",
                self.zip or "",
                (self.country_id and self.country_id.display_name) or "",
            ),
            "z": zoom,
        }
        return "https://maps.google.com/maps?" + urlencode(params)

    @api.depends("website_id")
    @api.depends_context("display_website", "uid")
    def _compute_display_name(self):
        super()._compute_display_name()
        if not self.env.context.get("display_website") or not self.env.user.has_group(
            "website.group_multi_website"
        ):
            return
        for partner in self:
            if partner.website_id:
                partner.display_name += f" [{partner.website_id.name}]"

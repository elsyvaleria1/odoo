from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SlideSlide(models.Model):
    _inherit = "slide.slide"

    @api.model
    def _search_get_detail(self, website, order, options):
        res = super()._search_get_detail(website, order, options)

        team = self.env["team.team"]
        if options.get("helpdesk"):
            team = team.browse(self.env["ir.http"]._unslug(options["helpdesk"])[1])

        if not team:
            return res

        extra_domain = [("is_category", "=", False)]
        if options.get("max_date"):
            extra_domain = [
                ("date_published", ">=", options["max_date"])
            ] + extra_domain
        if options.get("tag"):
            extra_domain = [
                "|",
                ("tag_ids.name", "ilike", options["tag"]),
                ("channel_id.tag_ids.name", "ilike", options["tag"]),
            ] + extra_domain
        website_slide_channel_ids = team.sudo().website_slide_channel_ids
        if website_slide_channel_ids:
            extra_domain = [
                ("channel_id", "in", website_slide_channel_ids.ids)
            ] + extra_domain
        res["base_domain"] = [res["base_domain"][0] + extra_domain]
        res["search_fields"].extend(
            ["channel_id.tag_ids.name", "tag_ids.name", "question_ids.question"]
        )
        _debug.pipeline(
            "slide_search_scoped",
            team=team,
            team_channels=website_slide_channel_ids,
            tagged=bool(options.get("tag")),
            date_bounded=bool(options.get("max_date")),
        )

        return res

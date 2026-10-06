from odoo.http import request, route
from odoo.libs.debug_log import DebugLog

from odoo.addons.website_helpdesk.controllers.main import WebsiteHelpdesk
from odoo.addons.website_slides.controllers.main import WebsiteSlides

_debug = DebugLog(__name__)


class WebsiteHelpdeskSlides(WebsiteHelpdesk):
    def _format_search_results(self, search_type, records, options):
        if search_type != "slides":
            return super()._format_search_results(search_type, records, options)

        _debug.pipeline("format_slide_results", model=records._name, records=records)
        if records._name == "slide.slide":
            return [
                {
                    "template": "website_helpdesk_slides.search_result",
                    "record": slide,
                    "score": slide.total_views
                    + slide.comments_count
                    + slide.likes
                    - slide.dislikes,
                    "url": slide.website_absolute_url
                    if slide.is_preview or slide.channel_id.is_member
                    else slide.channel_id.website_absolute_url,
                    "icon": "fa-graduation-cap",
                }
                for slide in records
            ]
        return [
            {
                "template": "website_helpdesk_slides.channel_search_result",
                "record": channel,
                "score": channel.total_views + channel.total_votes,
                "url": channel.website_absolute_url,
                "icon": "fa-graduation-cap",
            }
            for channel in records
        ]


class WebsiteSlidesHelpdesk(WebsiteSlides):
    @route(
        '/helpdesk/<model("team.team"):team>/slides',
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def helpdesk_slides_channel(self, team=None, **post):
        if not team or not team.use_helpdesk or not team.website_slide_channel_ids:
            _debug.lifecycle(
                "helpdesk_slides_redirect_index",
                team=team,
                use_helpdesk=bool(team) and team.use_helpdesk,
            )
            return request.redirect("/slides")
        channels = team.website_slide_channel_ids
        if len(channels) == 1:
            _debug.lifecycle(
                "helpdesk_slides_redirect_single", team=team, channel=channels
            )
            return request.redirect(
                "/slides/%s" % request.env["ir.http"]._slug(channels[0]), code=302
            )
        _debug.pipeline("helpdesk_courses_page", team=team, channels=channels)
        render_values = super().slides_channel_values(self, **post)
        render_values["channels"] = channels
        return request.render("website_helpdesk_slides.helpdesk_courses", render_values)

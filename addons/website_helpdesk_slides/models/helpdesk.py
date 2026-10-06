from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HelpdeskTeam(models.Model):
    _inherit = "team.team"

    show_knowledge_base_slide_channel = fields.Boolean(
        export_string_translation=False,
        compute="_compute_show_knowledge_base_slide_channel",
    )
    website_slide_channel_ids = fields.Many2many(
        comodel_name="slide.channel",
        string="Courses",
        help="Customers will see only the content from chosen courses in the help center. If you want all courses to be accessible, just leave the field empty. Alternatively, you can make courses private to restrict this feature to internal users.",
    )
    website_top_channels = fields.Many2many(
        comodel_name="slide.channel",
        string="Most Popular Courses",
        export_string_translation=False,
        compute="_compute_website_top_channels",
    )

    @api.depends("website_slide_channel_ids")
    def _compute_show_knowledge_base_slide_channel(self) -> None:
        accessible_channels = self.env["slide.channel"].search_count([], limit=1)
        accessible_all_teams_channels = set(
            self.sudo()
            .website_slide_channel_ids.sudo(False)
            ._filtered_access("read")
            .ids
        )
        for team in self:
            team_sudo = team.sudo()
            if not team_sudo.use_website_helpdesk_slides:
                team_sudo.sudo().show_knowledge_base_slide_channel = False
                continue
            team_channels = set(team_sudo.sudo().website_slide_channel_ids.ids)
            accessible_team_channels = team_channels & accessible_all_teams_channels
            team_sudo.sudo().show_knowledge_base_slide_channel = bool(
                team_channels and accessible_team_channels
            ) or bool(not team_channels and accessible_channels)
            _debug.logic(
                "knowledge_base_visibility",
                team=team,
                team_channels=len(team_channels),
                accessible=len(accessible_team_channels),
                any_channel=bool(accessible_channels),
                shown=team_sudo.show_knowledge_base_slide_channel,
            )

    def _compute_website_top_channels(self) -> None:
        teams_without_channel = self.filtered(
            lambda team: not team.website_slide_channel_ids
        )

        def filtered_channels(channel_ids):
            return channel_ids.filtered(
                lambda channel: (
                    channel.website_published
                    and (
                        channel.visibility == "public"
                        or (channel.visibility == "members" and channel.is_member)
                        or (
                            channel.visibility == "connected"
                            and not self.env.user._is_public()
                        )
                    )
                )
            )

        if teams_without_channel:
            with _debug.perf(
                "top_channels_fallback_search",
                cr=self.env.cr,
                teams=len(teams_without_channel),
            ) as span:
                channels = filtered_channels(
                    self.env["slide.channel"].search(
                        [("website_published", "=", True)], order="total_views desc"
                    )
                )[:5]
                span.set(channels=channels)

        for team in self:
            if team.website_slide_channel_ids:
                team.website_top_channels = filtered_channels(
                    team.website_slide_channel_ids
                ).sorted(key="total_views", reverse=True)[:5]
            else:
                team.website_top_channels = channels

    @api.model
    def _get_fields_knowledge_base(self):
        return super()._get_fields_knowledge_base() + [
            "show_knowledge_base_slide_channel"
        ]

    def _helpcenter_filter_types(self):
        res = super()._helpcenter_filter_types()
        if not self.show_knowledge_base_slide_channel:
            return res

        res["slides"] = self.env._("Courses")
        _debug.pipeline("filter_type_slides_offered", team=self)
        return res

    def _helpcenter_filter_tags(self, search_type):
        res = super()._helpcenter_filter_tags(search_type)
        if not self.show_knowledge_base_slide_channel or (
            search_type and search_type != "slides"
        ):
            return res

        course_tags = self.env["slide.tag"].search([])
        channel_tags = self.env["slide.channel.tag"].search([])
        _debug.pipeline(
            "filter_tags_slides",
            team=self,
            search_type=search_type,
            course_tags=course_tags,
            channel_tags=channel_tags,
        )
        return (
            res
            + course_tags.mapped(lambda t: t.name and t.name.lower())
            + channel_tags.mapped(lambda t: t.name and t.name.lower())
        )

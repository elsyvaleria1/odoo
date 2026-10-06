from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SlideChannel(models.Model):
    _inherit = "slide.channel"

    helpdesk_team_ids = fields.Many2many(
        comodel_name="team.team",
        relation="slide_channel_team_team_rel",
        column1="slide_channel_id",
        column2="team_team_id",
        domain=[("use_helpdesk", "=", True)],
    )
    helpdesk_team_count = fields.Count(
        count_of="helpdesk_team_ids",
        export_string_translation=False,
    )

    @api.model
    def _search_get_detail(self, website, order, options):
        res = super()._search_get_detail(website, order, options)

        team = self.env["team.team"]
        if options.get("helpdesk"):
            team = team.browse(self.env["ir.http"]._unslug(options["helpdesk"])[1])

        if not team:
            return res

        extra_domain = []
        if options.get("tag"):
            extra_domain = [("tag_ids.name", "ilike", options["tag"])]
        website_slide_channel_ids = team.sudo().website_slide_channel_ids
        if website_slide_channel_ids:
            extra_domain = Domain.AND(
                [[("id", "in", website_slide_channel_ids.ids)], extra_domain]
            )
        res["base_domain"] = [res["base_domain"][0] + extra_domain]
        _debug.pipeline(
            "channel_search_scoped",
            team=team,
            team_channels=website_slide_channel_ids,
            tagged=bool(options.get("tag")),
        )

        return res

    def action_view_helpdesk_teams(self):
        self.check_singleton()
        action_window = {
            "type": "ir.actions.act_window",
            "res_model": "team.team",
            "name": self.env._("%(name)s's Helpdesk Teams", name=self.name),
            "context": {
                "default_use_helpdesk": True,
                "default_use_website_helpdesk_form": True,
                "default_use_website_helpdesk_slides": True,
                "default_website_slide_channel_ids": [self.id],
            },
        }
        _debug.lifecycle(
            "view_helpdesk_teams", channel=self, teams=self.helpdesk_team_count
        )
        if self.helpdesk_team_count == 1:
            action_window.update(
                {
                    "res_id": self.helpdesk_team_ids.id,
                    "views": [(False, "form")],
                }
            )
        else:
            action_window.update(
                {
                    "domain": [("id", "in", self.helpdesk_team_ids.ids)],
                    "views": [(False, "list"), (False, "form"), (False, "kanban")],
                }
            )
        return action_window

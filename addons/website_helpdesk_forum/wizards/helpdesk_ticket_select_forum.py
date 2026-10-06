from odoo import fields, models
from odoo.fields import Domain


class ForumForum(models.Model):
    _inherit = "forum.forum"

    filter_for_helpdesk_wizard = fields.Boolean(
        search="_search_filter_for_helpdesk_wizard",
        store=False,
    )

    def _search_filter_for_helpdesk_wizard(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        ticket_id = self.env.context.get("active_id")
        forums = (
            self.env["helpdesk.ticket"]
            .browse(ticket_id)
            .team_id.sudo()
            .website_forum_ids
        )
        if not forums:
            return Domain.TRUE
        return [("id", operator, forums.ids)]

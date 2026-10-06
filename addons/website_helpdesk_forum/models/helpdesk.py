from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HelpdeskTeam(models.Model):
    _inherit = "team.team"

    show_knowledge_base_forum = fields.Boolean(
        export_string_translation=False,
        compute="_compute_show_knowledge_base_forum",
    )
    website_forum_ids = fields.Many2many(
        comodel_name="forum.forum",
        relation="forum_forum_team_team_rel",
        column1="team_team_id",
        column2="forum_forum_id",
        string="Forums",
        help="Customers will see only the posts from chosen forums in the help center. If you want all forums to be accessible, just leave the field empty. Alternatively, you can make forums private to restrict this feature to internal users.",
    )
    top_forum_posts = fields.Many2many(
        comodel_name="forum.post",
        string="Top Posts",
        compute="_compute_top_forum_posts",
        help="These are the top posts in the forums associated with this helpdesk team",
    )

    @api.depends("website_forum_ids")
    def _compute_show_knowledge_base_forum(self) -> None:
        accessible_forums = self.env["forum.forum"].search_count([], limit=1)
        accessible_all_teams_forums = set(
            self.sudo().website_forum_ids.sudo(False)._filtered_access("read").ids
        )
        for team in self:
            team_sudo = team.sudo()
            if not team_sudo.use_website_helpdesk_forum:
                team_sudo.sudo().show_knowledge_base_forum = False
                continue
            team_forums = set(team_sudo.sudo().website_forum_ids.ids)
            accessible_team_forums = team_forums & accessible_all_teams_forums
            team_sudo.sudo().show_knowledge_base_forum = bool(
                team_forums and accessible_team_forums
            ) or bool(not team_forums and accessible_forums)

    def _check_help_center_activated(self) -> bool:
        self.check_singleton()
        if not self.show_knowledge_base_forum:
            _debug.logic("help_center_refused", reason="forum_off", team=self.id)
            raise UserError(self.env._("Help Center is not active for this team."))
        return True

    @api.model
    def _get_fields_knowledge_base(self):
        return super()._get_fields_knowledge_base() + ["show_knowledge_base_forum"]

    def _helpcenter_filter_types(self):
        res = super()._helpcenter_filter_types()
        if not self.show_knowledge_base_forum:
            return res

        res["forum_posts_only"] = self.env._("Forum Posts")
        return res

    def _helpcenter_filter_tags(self, search_type):
        res = super()._helpcenter_filter_tags(search_type)
        if not self.show_knowledge_base_forum or (
            search_type and search_type != "forum_posts_only"
        ):
            return res

        tags = self.env["forum.tag"].search(
            [
                ("posts_count", ">", 0),
            ],
            order="posts_count desc",
            limit=20,
        )
        return res + tags.mapped(lambda t: t.name and t.name.lower())

    def _compute_top_forum_posts(self) -> None:
        for team in self:
            search_domain = [("parent_id", "=", False)]
            if team.website_forum_ids:
                search_domain.append(("forum_id", "in", team.website_forum_ids.ids))

            team.top_forum_posts = self.env["forum.post"].search(
                search_domain, order="vote_count desc, last_activity_date desc", limit=5
            )


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    forum_post_ids = fields.Many2many(
        comodel_name="forum.post",
        string="Forum Posts",
        export_string_translation=False,
        copy=False,
    )
    forum_post_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_forum_post_count",
    )
    use_website_helpdesk_forum = fields.Boolean(
        related="team_id.use_website_helpdesk_forum",
        string="Help Center Active",
        export_string_translation=False,
        readonly=True,
    )
    can_share_forum = fields.Boolean(
        export_string_translation=False,
        compute="_compute_can_share_forum",
    )

    @api.depends_context("uid")
    @api.depends("use_website_helpdesk_forum")
    def _compute_can_share_forum(self) -> None:
        forum_count = self.env["forum.forum"].search_count([])
        for ticket in self:
            ticket.can_share_forum = ticket.use_website_helpdesk_forum and forum_count

    @api.depends_context("uid")
    @api.depends("forum_post_ids")
    def _compute_forum_post_count(self) -> None:
        rg = self.env["forum.post"]._read_group(
            [("can_view", "=", True), ("id", "in", self.forum_post_ids.ids)],
            ["ticket_id"],
            ["__count"],
        )
        posts_count = {ticket.id: count for ticket, count in rg}
        for ticket in self:
            ticket.forum_post_count = posts_count.get(ticket.id, 0)

    def action_share_ticket_on_forum(self):
        self.check_singleton()
        self.team_id._check_help_center_activated()
        return self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "website_helpdesk_forum.helpdesk_ticket_select_forum_wizard_action"
        )

    def action_view_forum_posts(self, edit=False):
        self.check_singleton()
        self.team_id._check_help_center_activated()
        if not self.forum_post_ids:
            _debug.logic("forum_posts_refused", reason="no_posts", ticket=self.id)
            raise UserError(
                self.env._("There are no posts associated with this ticket.")
            )

        if len(self.forum_post_ids) > 1:
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "website_forum.forum_post_action_forum_main"
            )
            action["domain"] = [("id", "in", self.forum_post_ids.ids)]
            return action

        return self.forum_post_ids.open_forum_post(edit)

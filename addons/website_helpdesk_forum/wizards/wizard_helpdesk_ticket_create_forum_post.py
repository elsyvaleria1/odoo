from markupsafe import Markup

from odoo import Command, api, fields, models


class WizardHelpdeskTicketCreateForumPost(models.TransientModel):
    _name = "wizard.helpdesk.ticket.create.forum.post"
    _description = "Share on Forum"

    ticket_id = fields.Many2one(
        comodel_name="helpdesk.ticket",
        export_string_translation=False,
        default=lambda self: self.env.context.get("active_id"),
    )
    forum_id = fields.Many2one(
        comodel_name="forum.forum",
        required=True,
        domain="[('filter_for_helpdesk_wizard', '=', True)]",
    )

    title = fields.Char(
        compute="_compute_post",
        store=True,
        readonly=False,
        required=True,
    )
    description = fields.Html(
        compute="_compute_post",
        store=True,
        readonly=False,
        required=True,
    )
    answer_content = fields.Html(string="Answer")
    tag_ids = fields.Many2many(
        comodel_name="forum.tag",
        string="Tags",
        compute="_compute_post",
        store=True,
        readonly=False,
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if "forum_id" in fields:
            res["forum_id"] = (
                self.env["forum.forum"]
                .search([("filter_for_helpdesk_wizard", "=", True)], limit=1)
                .id
            )
        return res

    @api.depends("ticket_id")
    def _compute_post(self) -> None:
        tags_lower = self.ticket_id.tag_ids.mapped(lambda t: t and t.name.lower())
        all_tags = {}
        if tags_lower:
            self.env.cr.execute(
                """SELECT id, LOWER(name) FROM forum_tag WHERE LOWER(name) = ANY(%s)""",
                (list(tags_lower),),
            )
            all_tags = {t[1]: t[0] for t in self.env.cr.fetchall()}

        for wizard in self:
            wizard.title = wizard.ticket_id.name
            wizard.description = wizard.ticket_id.description

            ticket_tags = wizard.ticket_id.tag_ids.mapped(
                lambda t: t and t.name.lower()
            )
            wizard.write(
                {
                    "tag_ids": [
                        Command.set([all_tags[t] for t in ticket_tags if t in all_tags])
                    ]
                }
            )

    def _create_forum_post(self):
        self.check_singleton()
        self.ticket_id.team_id._check_help_center_activated()

        forum_post = self.env["forum.post"].create(
            {
                "name": self.title,
                "forum_id": self.forum_id.id,
                "content": self.description,
                "ticket_id": self.ticket_id.id,
                "tag_ids": [Command.set(self.tag_ids.ids)],
            }
        )
        if self.answer_content:
            self.env["forum.post"].create(
                {
                    "forum_id": self.forum_id.id,
                    "content": self.answer_content,
                    "ticket_id": self.ticket_id.id,
                    "is_correct": True,
                    "parent_id": forum_post.id,
                }
            )
        body = Markup("<a href='/forum/%s/question/%s'>%s</a> %s") % (
            self.forum_id.id,
            forum_post.id,
            forum_post.name,
            self.env._("Forum Post Created"),
        )
        self.ticket_id.message_post(body=body)
        self.ticket_id.write({"forum_post_ids": [Command.link(forum_post.id)]})

        for post in forum_post:
            post.message_post_with_source(
                "helpdesk.ticket_creation",
                render_values={"self": post, "ticket": self.ticket_id},
                subtype_xmlid="mail.mt_note",
            )

        return forum_post

    def action_create_post(self) -> dict:
        self._create_forum_post()
        return {"type": "ir.actions.act_window_close"}

    def action_create_view_post(self):
        return self._create_forum_post().open_forum_post()

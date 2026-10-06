from odoo import api, fields, models


class HelpdeskTeam(models.Model):
    _inherit = "team.team"

    show_knowledge_base_article = fields.Boolean(
        export_string_translation=False,
        compute="_compute_show_knowledge_base_article",
    )
    website_article_id = fields.Many2one(
        comodel_name="knowledge.article",
        string="Article",
        help="Article on which customers will land by default, and to which the search will be restricted.",
    )
    website_latest_articles = fields.Many2many(
        comodel_name="knowledge.article",
        string="Latest Articles",
        export_string_translation=False,
        compute="_compute_latest_articles",
    )

    @api.depends("website_article_id")
    def _compute_show_knowledge_base_article(self) -> None:
        accessible_articles = (
            self.env["knowledge.article"].search_count(
                [
                    ("website_published", "=", True),
                    ("name", "!=", False),
                    ("is_article_item", "=", False),
                    ("is_template", "=", False),
                ],
                limit=1,
            )
            > 0
        )
        for team_sudo in self.sudo():
            team_sudo.show_knowledge_base_article = (
                team_sudo.use_website_helpdesk_knowledge and accessible_articles
            )

    def _compute_latest_articles(self) -> None:
        latest_articles = self.env["knowledge.article"].search(
            [
                ("website_published", "=", True),
                ("name", "!=", False),
                ("is_article_item", "=", False),
                ("is_template", "=", False),
            ],
            limit=5,
            order="favorite_count desc, write_date desc",
        )
        for team in self:
            team.website_latest_articles = latest_articles

    @api.model
    def _get_fields_knowledge_base(self):
        return super()._get_fields_knowledge_base() + ["show_knowledge_base_article"]

    def _helpcenter_filter_types(self):
        res = super()._helpcenter_filter_types()
        if not self.show_knowledge_base_article:
            return res

        res["knowledge"] = self.env._("Articles")
        return res

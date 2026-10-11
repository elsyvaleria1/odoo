from odoo import api, fields, models

from odoo.addons.ai.utils.html_extractor import HTMLExtractor


class AIAgentSource(models.Model):
    _name = "ai.agent.source"
    _inherit = ["ai.agent.source"]

    article_id = fields.Many2one(
        comodel_name="knowledge.article",
        string="Source Article",
    )
    type = fields.Selection(
        selection_add=[("knowledge_article", "Knowledge Article")],
        ondelete={"knowledge_article": lambda recs: recs.write({"type": "binary"})},
    )

    @api.model
    def create_from_articles(self, article_ids, agent_id) -> None:
        articles = self.env["knowledge.article"].browse(article_ids)
        vals_list = [
            {
                "name": article.name,
                "agent_id": agent_id,
                "article_id": article.id,
                "url": article.article_url,
                "type": "knowledge_article",
            }
            for article in articles
        ]
        sources = super().create(vals_list)
        if sources:
            self.env["ir.cron"]._trigger_ref("ai.ir_cron_process_sources")

    @api.depends_context("uid")
    @api.depends("article_id")
    def _compute_user_has_access(self) -> None:
        article_sources = self.filtered(lambda s: s.type == "knowledge_article")
        for source in article_sources:
            source.user_has_access = source.article_id.with_user(
                self.env.user
            ).user_can_read
        super(AIAgentSource, self - article_sources)._compute_user_has_access()

    def _update_name(self):
        if not self:
            return None

        source = self[0]

        if source.type != "knowledge_article":
            return super()._update_name()

        current_name = source.article_id.name
        if source.name != current_name:
            source.name = current_name
        return None

    def action_access_source(self) -> dict:
        self.check_singleton()
        if self.url:
            return {
                "type": "ir.actions.act_url",
                "url": self.url,
                "target": "new",
            }
        return super().action_access_source()

    def _get_sources_to_process(self):
        sources_to_process = super()._get_sources_to_process()
        target_articles = (
            self.env["ai.agent.source"]
            .search(
                [
                    ("type", "=", "knowledge_article"),
                    ("status", "=", "processing"),
                ]
            )
            .mapped("article_id")
        )
        knowledge_sources_to_process = self.env["ai.agent.source"].search(
            [
                ("article_id", "in", target_articles.ids),
            ]
        )
        return sources_to_process | knowledge_sources_to_process

    def _get_content(self, source):
        if source.type != "knowledge_article":
            return super()._get_content(source)

        lang = source.agent_id.create_uid.lang or "en_US"
        env = self.with_context(lang=lang).env
        extractor = HTMLExtractor(env)

        parent_article = source.article_id
        article_descendants = parent_article._get_descendants()
        all_articles = article_descendants | parent_article
        content = ""
        for article in all_articles:
            result = extractor.extract_from_html(article.body)
            if result and result["content"]:
                content += result["content"] + "\n"
            else:
                return {
                    "content": None,
                    "error": result.get(
                        "error", env._("Failed to extract content from the articles.")
                    ),
                }
        return {"content": content, "error": None}

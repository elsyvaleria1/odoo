from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.knowledge.controllers.main import KnowledgeController

_debug = DebugLog(__name__)


class KnowledgeWebsiteController(KnowledgeController):
    @http.route(
        "/knowledge/home", type="http", auth="public", website=True, sitemap=False
    )
    def access_knowledge_home(self):
        if request.env.user._is_public():
            article = request.env["knowledge.article"]._get_first_accessible_article()
            if not article:
                _debug.logic("knowledge_refused", reason="no_public_article", by="home")
                raise NotFound
            return request.redirect("/knowledge/article/%s" % article.id)
        return super().access_knowledge_home()

    @http.route(
        "/knowledge/article/<int:article_id>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        multilang=False,
    )
    def redirect_to_article(self, **kwargs):
        if request.env.user._is_public():
            article = (
                request.env["knowledge.article"].sudo().browse(kwargs["article_id"])
            )
            if not article.exists():
                _debug.logic(
                    "knowledge_refused",
                    reason="missing",
                    article=kwargs["article_id"],
                )
                raise NotFound
            if article.website_published:
                return self._redirect_to_public_view(
                    article, kwargs.get("no_sidebar", False)
                )
            return request.redirect(
                "/web/login?redirect=/knowledge/article/%s" % kwargs["article_id"]
            )
        return super().redirect_to_article(**kwargs)

    def _redirect_to_public_view(self, article, no_sidebar=False):
        return request.render(
            "website_knowledge.article_view_public",
            {
                "article": article,
                "main_object": article,
                "show_sidebar": bool(
                    not no_sidebar
                    and (
                        article.parent_id.website_published
                        or article.child_ids.filtered("website_published")
                    )
                ),
            },
        )

    @http.route("/knowledge/public/children", type="jsonrpc", auth="public")
    def get_public_article_children(self, article_id):
        return request.env["knowledge.article"].search_read(
            [("parent_id", "=", article_id), ("is_article_item", "=", False)],
            ["icon", "name"],
            order="sequence",
        )

    @http.route("/knowledge/public/article", type="jsonrpc", auth="public")
    def get_public_article_content(self, article_id):
        article = self.env["knowledge.article"].browse(article_id)
        if not article or not article.website_published:
            _debug.logic("knowledge_refused", reason="unpublished", article=article_id)
            raise NotFound
        article_data = self._prepare_public_article(article)
        return {
            "content": request.env["ir.qweb"]._render(
                "website_knowledge.article_public_content",
                {
                    "article": article_data,
                    "show_sidebar": True,
                },
            )
        }

    @http.route("/knowledge/public/sidebar", type="jsonrpc", auth="public")
    def get_public_sidebar_articles(self, article_id):
        accessible_ancestors_ids = (
            self.env["knowledge.article"]
            .browse(article_id)
            ._get_accessible_root_ancestors()
            .ids
        )
        return request.env["knowledge.article"].search_read(
            [
                ("is_article_item", "=", False),
                "|",
                ("id", "in", accessible_ancestors_ids),
                ("parent_id", "in", accessible_ancestors_ids),
                ("parent_id", "!=", article_id),
            ],
            ["icon", "name", "parent_id"],
            order="parent_id desc, sequence",
            load=False,
        )

    @http.route("/knowledge/public/search", type="jsonrpc", auth="public")
    def search_public_article(self, subsite_root_id, search_value):
        sorted_articles = request.env["knowledge.article"].get_sorted_articles(
            search_value,
            [("website_published", "=", True), ("id", "child_of", subsite_root_id)],
        )
        for article in sorted_articles:
            del article["is_user_favorite"]
            del article["root_article_id"]
        return sorted_articles

    def _prepare_public_article(self, article):
        public_fields = {
            "body",
            "cover_image_position",
            "cover_image_url",
            "display_name",
            "full_width",
            "icon",
        }
        public_article = {field: article[field] for field in public_fields}
        public_article["cover_image_id"] = article.cover_image_id.id
        public_article["id"] = article.id
        return public_article

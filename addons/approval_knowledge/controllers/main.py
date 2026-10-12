from typing import TYPE_CHECKING

from werkzeug.exceptions import BadRequest

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.approval_knowledge.models.knowledge_article import (
    ARTICLE_ACCESS_ROLES,
)
from odoo.addons.knowledge.controllers.main import KnowledgeController

if TYPE_CHECKING:
    from odoo.addons.approval_knowledge.models.knowledge_article import (
        KnowledgeArticle,
    )


def _requestable_article(article_id: int) -> KnowledgeArticle:
    if not request.env.user._is_internal():
        return request.env["knowledge.article"]
    article_sudo = (
        request.env["knowledge.article"]
        .sudo()
        .with_context(active_test=False)
        .browse(article_id)
        .exists()
    )
    if not article_sudo or article_sudo.with_user(request.env.user).user_has_access:
        return request.env["knowledge.article"]
    return article_sudo


class KnowledgeAccessRequestController(KnowledgeController):
    @http.route()
    def redirect_to_article(self, article_id, show_resolved_threads=False):
        if _requestable_article(article_id):
            return request.redirect(f"/knowledge/article/{article_id}/request_access")
        return super().redirect_to_article(
            article_id, show_resolved_threads=show_resolved_threads
        )

    @http.route(
        "/knowledge/article/<int:article_id>/request_access",
        type="http",
        auth="user",
        methods=["GET", "POST"],
    )
    def article_request_access(self, article_id, role=None, **kwargs):
        article_sudo = _requestable_article(article_id)
        if not article_sudo:
            return request.redirect(f"/knowledge/article/{article_id}")
        partner = request.env.user.partner_id
        values = {"article_id": article_id, "requested_role": False, "error": ""}
        if request.httprequest.method == "POST":
            if role not in ARTICLE_ACCESS_ROLES:
                raise BadRequest
            try:
                article_sudo._request_access(partner, role)
                values["requested_role"] = role
            except UserError as error:
                values["error"] = error.args[0]
        else:
            values["requested_role"] = next(
                (
                    held
                    for held in ARTICLE_ACCESS_ROLES
                    if article_sudo._get_live_access_request(partner, held)
                ),
                False,
            )
        return request.render("approval_knowledge.article_request_access", values)

from odoo import http
from odoo.http import request

from odoo.addons.knowledge.controllers.main import KnowledgeController
from odoo.addons.mail.controllers.thread import ThreadController
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.portal.controllers.mail import MailController


class ArticleThreadController(KnowledgeController):
    @http.route("/knowledge/thread/create", type="jsonrpc", auth="user")
    def create_thread(
        self,
        article_id,
        article_anchor_text="",
        fields=["id", "article_anchor_text"],
    ):
        article_thread = request.env["knowledge.article.thread"].create(
            {
                "article_id": article_id,
                "article_anchor_text": article_anchor_text,
            }
        )
        return article_thread.read(fields)[0]

    @http.route("/knowledge/thread/resolve", type="http", auth="user")
    def resolve_thread(self, res_id, token):
        _, thread, redirect = MailController._get_token_record_and_redirect(
            "knowledge.article.thread", int(res_id), token
        )
        if not thread or not thread.article_id.user_can_write:
            return redirect
        if not thread.is_resolved:
            thread.is_resolved = True
        return self.redirect_to_article(
            thread.article_id.id, show_resolved_threads=True
        )


class KnowledgeThreadController(ThreadController):
    @http.route(
        "/knowledge/threads/messages", methods=["POST"], type="jsonrpc", auth="user"
    )
    def mail_threads_messages(self, thread_model, thread_ids, limit=30):
        thread_ids = [int(thread_id) for thread_id in thread_ids]
        output = {}
        for thread_id in thread_ids:
            domain = self._get_domain_thread_messages(thread_model, thread_id)
            res = request.env["mail.message"]._message_fetch(domain, limit=limit)
            messages = res.pop("messages")
            output[thread_id] = {
                **res,
                "data": Store().add(messages).get_result(),
                "messages": messages.ids,
            }
        return output

    def _get_domain_thread_messages(self, thread_model, thread_id):
        return [
            ("res_id", "=", int(thread_id)),
            ("model", "=", thread_model),
            ("message_type", "=", "comment"),
            (
                "subtype_id",
                "=",
                request.env.ref("mail.mt_comment").id,
            ),
            ("is_internal", "=", False),
        ]

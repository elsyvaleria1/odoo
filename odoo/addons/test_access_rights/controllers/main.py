from odoo import http
from odoo.http import request


class SharedDocController(http.Controller):
    @http.route(
        "/test_access_rights/shared/<int:doc_id>",
        type="http",
        auth="link",
        link="test_access_right.shared_doc:doc_id",
        methods=["GET"],
    )
    def shared_doc(self, doc_id, **kwargs):
        return request.prepare_json_response(
            {"id": request.link_subject.id, "link": request.access_link.id or False}
        )

    @http.route(
        "/test_access_rights/shared_edit/<int:doc_id>",
        type="http",
        auth="link",
        link="test_access_right.shared_doc:doc_id",
        link_role="edit",
        methods=["GET"],
    )
    def shared_doc_edit(self, doc_id, **kwargs):
        return request.prepare_json_response({"id": request.link_subject.id})

    @http.route(
        "/test_access_rights/shared_or_home/<int:doc_id>",
        type="http",
        auth="link",
        link="test_access_right.shared_doc:doc_id",
        link_refused="/my",
        methods=["GET"],
    )
    def shared_doc_or_home(self, doc_id, **kwargs):
        return request.prepare_json_response(
            {"id": request.link_subject.id, "su": request.link_subject.env.su}
        )

    @http.route(
        "/test_access_rights/node/<int:node_id>",
        type="http",
        auth="link",
        link="test_access_right.graph_node:node_id",
        methods=["GET"],
    )
    def node(self, node_id, **kwargs):
        return request.prepare_json_response({"id": request.link_subject.id})

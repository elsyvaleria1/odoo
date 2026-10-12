from odoo import http
from odoo.http import request

from odoo.addons.rpc.controllers.doc import DocController


class DocClientController(DocController):
    @http.route(
        ["/doc", "/doc/<model_name>", "/doc/index.html"], type="http", auth="user"
    )
    def doc_client(self, model_name: str | None = None, **kwargs):
        self._check_doc_access()
        res = request.render("api_doc.docclient")
        res.headers["X-Frame-Options"] = "deny"
        return res

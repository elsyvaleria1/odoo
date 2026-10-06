from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.binary import Binary
from odoo.addons.web.models.ir_asset import UNIT_TEST_URL_SEGMENT


class WebsiteBinary(Binary):
    @http.route(
        ["/web/assets/<int:website_id>/<unique>/<string:filename>"],
        type="http",
        auth="public",
        readonly=True,
    )
    def content_assets_website(self, website_id=None, **kwargs):
        return super().content_assets(
            **kwargs, assets_params=self._website_params(website_id)
        )

    @http.route(
        [
            (
                f"/web/assets/{UNIT_TEST_URL_SEGMENT}/<string:scope>"
                "/<int:website_id>/<unique>/<string:filename>"
            )
        ],
        type="http",
        auth="public",
        readonly=True,
    )
    def content_assets_scoped_website(self, scope, website_id, **kwargs):
        return super().content_assets(
            **kwargs,
            assets_params={
                **self._unit_test_scope_params(scope, kwargs.get("filename")),
                **self._website_params(website_id),
            },
        )

    def _website_params(self, website_id):
        if not request.env["website"].browse(website_id).exists():
            raise request.prepare_not_found_error()
        return {"website_id": website_id}

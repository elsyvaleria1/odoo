import logging
from datetime import UTC, datetime, timedelta

from odoo import fields, http
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools import consteq

from odoo.addons.sale_lazada import utils

_logger = logging.getLogger(__name__)


class LazadaController(http.Controller):
    @http.route(
        '/lazada/return_from_authorization/<model("lazada.shop"):shop>/<int:timestamp>/<string:sign>',
        type="http",
        methods=["GET"],
        auth="user",
    )
    def lazada_return_from_authorization(self, shop, timestamp, sign, code=False):

        if datetime.fromtimestamp(timestamp, UTC).replace(
            tzinfo=None
        ) < fields.Datetime.now() - timedelta(minutes=30):
            raise AccessError(request.env._("The request is expired."))

        check_sign = utils.get_public_sign(shop, timestamp)
        if not consteq(sign, check_sign):
            raise AccessError(request.env._("The request signature is not valid."))

        if not consteq(request.params.get("state"), shop.lazada_oauth_state):
            raise AccessError(request.env._("Invalid OAuth state"))
        shop.lazada_oauth_state = False

        try:
            shop_vals = shop._prepare_shop_vals(code)
            shop.write(shop_vals)
            response = utils.send_lazada_api_request("GetSeller", shop, params={})
            seller_data = response["data"]
            shop.name = request.env._(
                "Lazada Shop - %(name)s", name=seller_data["name"]
            )

            shop_url = f"/odoo/action-sale_lazada.action_lazada_shop_list/{shop.id}"
            return request.redirect(shop_url, local=False)

        except utils.LazadaApiError as error:
            error_message = str(error) or request.env._(
                "An unexpected error occurred during authorization."
            )
            _logger.exception(
                "Failed to authorize Lazada shop %s: %s", shop.id, error_message
            )

            return request.redirect(
                f"/odoo/action-sale_lazada.action_lazada_shop_authorization_error/{shop.id}"
            )

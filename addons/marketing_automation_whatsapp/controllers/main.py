from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request


class MarketingAutomationWhatsappController(http.Controller):
    @http.route("/r/<string:code>/w/<int:whatsapp_id>", type="http", auth="public")
    def whatsapp_short_link_redirect(self, code, whatsapp_id, **post):
        wa_message_id = (
            request.env["whatsapp.message"].sudo().browse(whatsapp_id).exists().id
        )

        # Through the shared helper: this route used to record the click and
        # resolve the code separately -- two lookups of the same row -- and it
        # never checked `is_a_bot`, so link previewers counted as clicks.
        redirect_url = request.env["link.tracker"]._resolve_and_track(
            code,
            ip=request.httprequest.remote_addr,
            country_code=request.geoip.country_code,
            whatsapp_message_id=wa_message_id,
        )
        if not redirect_url:
            raise NotFound
        return request.redirect(redirect_url, code=301, local=False)

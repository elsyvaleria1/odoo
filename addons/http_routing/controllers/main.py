import logging

from odoo import http
from odoo.http import request

from odoo.addons.http_routing.models.ir_http import FRONTEND_TRANSLATIONS_ROUTE
from odoo.addons.web.controllers.session import Session
from odoo.addons.web.controllers.webclient import WebClient

_logger = logging.getLogger(__name__)


class Routing(http.Controller):
    @http.route(
        FRONTEND_TRANSLATIONS_ROUTE,
        type="http",
        auth="public",
        readonly=True,
        sitemap=False,
    )
    def get_website_translations(self, hash=None, lang=None, mods=None):
        modules = request.env["ir.http"]._get_translation_frontend_modules_name()
        if mods:
            _logger.debug(
                "Ignoring caller-supplied mods=%r on %s; serving %s",
                mods,
                request.httprequest.path,
                modules,
            )
        return WebClient().translations(hash, mods=",".join(modules), lang=lang)


class SessionWebsite(Session):
    @http.route("/web/session/logout", website=True, multilang=False, sitemap=False)
    def logout(self, redirect="/odoo"):
        return super().logout(redirect=redirect)

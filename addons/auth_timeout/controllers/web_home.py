from odoo import http

from odoo.addons.web.controllers import home as web_home


class Home(web_home.Home):
    @http.route(check_identity=False)
    def web_load_menus(self, lang=None, hash=None):
        return super().web_load_menus(lang, hash)

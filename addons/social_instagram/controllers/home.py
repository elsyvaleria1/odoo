from odoo.addons.web.controllers.home import Home


class InstagramHome(Home):
    def _get_allowed_robots_routes(self):
        return super()._get_allowed_robots_routes() + ["/social_instagram/"]

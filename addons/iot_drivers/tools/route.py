import logging

from odoo import http

from odoo.addons.iot_drivers.tools.system import IS_RPI

_logger = logging.getLogger(__name__)


def iot_route(route=None, linux_only=False, **kwargs):
    if "auth" not in kwargs:
        kwargs["auth"] = "none"
    if "save_session" not in kwargs:
        kwargs["save_session"] = False

    http_decorator = http.route(route, **kwargs)

    def decorator(endpoint):
        if linux_only and not IS_RPI:
            return None
        return http_decorator(endpoint)

    return decorator

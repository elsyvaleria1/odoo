import collections

from werkzeug.exceptions import Forbidden

import odoo.http
from odoo.http import JsonRPCDispatcher, serialize_exception

from odoo.addons.iot_drivers.tools.system import IS_TEST


class JsonRPCDispatcherPatch(JsonRPCDispatcher):
    def prepare_error_response(self, exc: Exception) -> collections.abc.Callable:
        error = {
            "code": 200,
            "message": "Odoo Server Error",
            "data": serialize_exception(exc),
        }
        if isinstance(exc, Forbidden):
            error["code"] = 403
            error["message"] = "403: Forbidden"
            error["data"] = {
                "message": error["data"]["message"]
            }

        return self._response(error=error)


if not IS_TEST:

    def get_dbs_served(self, host=None):
        return []

    odoo.http.Application.get_dbs_served = get_dbs_served

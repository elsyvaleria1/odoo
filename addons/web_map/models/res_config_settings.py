import requests

from odoo import api, fields, models
from odoo.http import request
from odoo.tools import consteq

MAP_BOX_PROBE_URL = (
    "https://api.mapbox.com/directions/v5/mapbox/driving/"
    "-73.989%2C40.733%3B-74%2C40.733"
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    map_box_token = fields.Char(
        string="Token Map Box",
        default="",
        config_parameter="web_map.token_map_box",
        help="Necessary for some functionalities in the map view",
    )

    def _check_map_box_token(self, url, headers, params):
        try:
            result = self.env["ir.egress"].request(
                "HEAD", url, purpose="mapbox", headers=headers, params=params, timeout=5
            )
            return result.status_code
        except requests.exceptions.RequestException:
            return 500

    def _get_map_box_referer(self):
        if not request:
            return None
        return request.httprequest.headers.environ.get("HTTP_REFERER")

    @api.onchange("map_box_token")
    def _onchange_map_box_token(self) -> dict | None:
        if not self.map_box_token:
            return None
        stored_token = self.env["ir.config_parameter"].get_param(
            "web_map.token_map_box"
        )
        if consteq(self.map_box_token, stored_token):  # noqa: E8537 -- outbound: a key we present to an outside service
            return None

        referer = self._get_map_box_referer()
        status_code = self._check_map_box_token(
            MAP_BOX_PROBE_URL,
            {"referer": referer} if referer else {},
            {
                "access_token": self.map_box_token,
                "steps": "true",
                "geometries": "geojson",
            },
        )
        if status_code == 200:
            return None

        self.map_box_token = ""
        messages = {
            401: self.env._("The token input is not valid"),
            403: self.env._("This referer is not authorized"),
            500: self.env._("The MapBox server is unreachable"),
        }
        return {
            "warning": {
                "message": messages.get(
                    status_code,
                    self.env._(
                        "The token could not be validated (HTTP %(status)s)",
                        status=status_code,
                    ),
                )
            }
        }

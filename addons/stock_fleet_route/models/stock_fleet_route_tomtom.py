import requests

from odoo import api, models
from odoo.exceptions import UserError
from odoo.libs import redact

from odoo.addons.integration.tools import register_url_secret

SERVICE_CODE = "tomtom_routing"
TOMTOM_ROUTE_PATH = "/routing/1/calculateRoute/{points}/json"
KEY_PURPOSE = "stock_fleet_route:tomtom_routing"
TIMEOUT = 15

# Routing v1 takes its key in the query string only, and a parameter named
# plain `key` is not one the generic masking recognises as a secret.
register_url_secret(
    r"(/routing/\d+/[^\s'\"<>]*?[?&]key=)[^&\s'\"<>]+", rf"\g<1>{redact.MASK}"
)


class StockFleetRouteTomtom(models.AbstractModel):
    """Client of TomTom's Routing API, for trucks with live traffic."""

    _name = "stock.fleet.route.tomtom"
    _description = "TomTom Routing"

    @api.model
    def _connection(self, company):
        """Return the connection holding ``company``'s TomTom credential.

        :param recordset company: the company the trip belongs to
        :raise UserError: when no usable credential serves the company
        :rtype: recordset
        """
        service = (
            self.env["integration.service"]
            .sudo()
            .search([("code", "=", SERVICE_CODE), ("active", "=", True)], limit=1)
        )
        if not service:
            raise UserError(
                self.env._(
                    "The outbound endpoint %s is missing or archived.", SERVICE_CODE
                )
            )
        connection = self.env["integration.connection"]._resolve(
            service, company=company
        )
        credential = connection.credential_id
        if not credential:
            raise UserError(
                self.env._(
                    "No TomTom API key for %(company)s. Create a credential for the "
                    "outbound endpoint %(endpoint)s, in its %(environment)s "
                    "environment, under Integrations > API Transport > "
                    "Configuration > Credentials.",
                    company=company.display_name,
                    endpoint=service.display_name,
                    environment=dict(
                        service._fields["environment"]._description_selection(self.env)
                    )[service.environment],
                )
            )
        if credential.is_expired:
            raise UserError(
                self.env._(
                    "The TomTom API key %s has expired.", credential.display_name
                )
            )
        return connection

    @api.model
    def _calculate_route(
        self, points, best_order=False, depart_at="now", company=None
    ) -> dict:
        """Drive through ``points`` from the first to the last.

        :param list points: (latitude, longitude) pairs, origin first
        :param bool best_order: let TomTom reorder the points between the
            first and the last
        :param str depart_at: ``now`` or an RFC 3339 date
        :param recordset company: whose TomTom credential pays for the call;
            the current company when omitted
        :return: ``order``, the indexes of the intermediate points (0 is
            ``points[1]``) in the order to visit them, and ``legs``, one dict per
            leg in that order with ``seconds``, ``delay`` and ``meters``
        :rtype: dict
        """
        connection = self._connection(company or self.env.company)
        path = TOMTOM_ROUTE_PATH.format(
            points=":".join(f"{lat},{lon}" for lat, lon in points)
        )
        params = {
            "traffic": "true",
            "computeBestOrder": "true" if best_order else "false",
            "routeType": "fastest",
            "travelMode": "truck",
            "departAt": depart_at,
        }
        data = self._tomtom_request(connection, path, params)
        route = (data.get("routes") or [{}])[0]
        legs = [
            {
                "seconds": leg["summary"].get("travelTimeInSeconds", 0),
                "delay": leg["summary"].get("trafficDelayInSeconds", 0),
                "meters": leg["summary"].get("lengthInMeters", 0),
            }
            for leg in route.get("legs", [])
        ]
        stops = len(points) - 2
        order = list(range(stops))
        optimized = data.get("optimizedWaypoints")
        if best_order and optimized:
            order = [
                waypoint["providedIndex"]
                for waypoint in sorted(optimized, key=lambda w: w["optimizedIndex"])
            ]
        return {"order": order, "legs": legs}

    @api.model
    def _tomtom_request(self, connection, path, params):
        """Call TomTom through ``connection`` and return its JSON answer.

        :param recordset connection: the connection holding the credential
        :param str path: the path under the connection's base URL
        :param dict params: the query, without the key
        :raise UserError: when TomTom is unreachable or answers an error
        :rtype: dict
        """
        key = connection.credential_id._use_secret(KEY_PURPOSE, prefer="api_key")
        if not key:
            raise UserError(
                self.env._(
                    "The TomTom credential %s holds no API key.",
                    connection.credential_id.display_name,
                )
            )
        try:
            response = connection._egress_request(
                "GET",
                connection._base_url().rstrip("/") + path,
                purpose="tomtom_routing",
                params={"key": key, **params},
                timeout=TIMEOUT,
            )
        except requests.RequestException as error:
            # Not chained: the cause's own message carries the URL with the key.
            raise UserError(
                self.env._(
                    "TomTom could not be reached: %s", redact.mask_text(str(error))
                )
            ) from None
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not response.ok:
            message = (
                data.get("detailedError", {}).get("message")
                or data.get("error", {}).get("description")
                or response.text[:300]
            )
            raise UserError(self.env._("TomTom answered: %s", message))
        return data

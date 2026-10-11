from odoo.http import Controller, request, route


class LocationSelectorController(Controller):
    @route("/delivery/set_pickup_location", type="jsonrpc", auth="user")
    def delivery_set_pickup_location(self, order_id, pickup_location_data):
        order = request.env["sale.order"].browse(order_id)
        order._set_pickup_location(pickup_location_data)

    @route("/delivery/get_pickup_locations", type="jsonrpc", auth="user")
    def delivery_get_pickup_locations(self, order_id, zip_code=None):
        order = request.env["sale.order"].browse(order_id)
        if request.geoip.country_code:
            country = request.env["res.country"].search(
                [("code", "=", request.geoip.country_code)],
                limit=1,
            )
        else:
            country = order.partner_shipping_id.country_id
        return order._get_pickup_locations(zip_code, country)

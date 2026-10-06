from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

from .sendcloud_locations_request import SendcloudLocationsRequest

LAST_MILE_T = "last_mile"
LAST_MILE_SERVICES_T = ["service_point", "locker", "locker_or_service_point"]
_debug = DebugLog(__name__)
LAST_MILE_H = "Last mile"
LAST_MILE_SERVICES_H = ["Service point", "Locker", "Locker or service point"]


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    sendcloud_can_customize_use_locations = fields.Boolean(
        compute="_compute_sendcloud_can_customize_use_locations",
        default=False,
    )
    sendcloud_use_locations = fields.Boolean(
        string="Use Sendcloud Locations",
        compute="_compute_sendcloud_use_locations",
        default=False,
        store=True,
        help="Allows the ecommerce user to choose a pick-up point as delivery address.",
    )
    sendcloud_locations_radius_value = fields.Integer(
        string="Sendcloud Locations Radius",
        default=10,
        required=True,
        help="Maximum locations distance radius.",
    )
    sendcloud_locations_radius_unit = fields.Many2one(
        comodel_name="uom.uom",
        compute="_compute_sendcloud_locations_radius_unit",
        search="_search_sendcloud_locations_radius_unit",
        default=lambda self: self.env.ref("uom.product_uom_km"),
        store=True,
    )
    sendcloud_locations_radius_unit_name = fields.Char(
        related="sendcloud_locations_radius_unit.display_name",
        string="Sendcloud Radius Unit Name",
    )
    sendcloud_locations_id = fields.Integer(string="Locations Id")

    @api.depends("sendcloud_shipping_id")
    def _compute_sendcloud_can_customize_use_locations(self):
        self.sendcloud_can_customize_use_locations = False
        for sc_carrier in self:
            product_func = sc_carrier.sendcloud_shipping_id.functionalities
            if not product_func:
                continue
            last_mile_custo = product_func.get("customizable", {}).get(LAST_MILE_T)
            if last_mile_custo and any(
                service in last_mile_custo for service in LAST_MILE_SERVICES_T
            ):
                sc_carrier.sendcloud_can_customize_use_locations = True

    @api.depends("sendcloud_shipping_id")
    def _compute_sendcloud_use_locations(self):
        for sc_carrier in self:
            product_func = sc_carrier.sendcloud_shipping_id.functionalities
            if not product_func:
                sc_carrier.sendcloud_use_locations = False
                continue
            if not sc_carrier.sendcloud_can_customize_use_locations and any(
                service in product_func.get("detail_func", {}).get(LAST_MILE_H, {})
                for service in LAST_MILE_SERVICES_H
            ):
                sc_carrier.sendcloud_use_locations = True
            else:
                sc_carrier.sendcloud_use_locations = False

    def _compute_sendcloud_locations_radius_unit(self):
        for carrier in self:
            carrier.sendcloud_locations_radius_unit = self._get_pickup_radius_uom()

    def _search_sendcloud_locations_radius_unit(self, operator, value) -> list:
        return [("sendcloud_locations_radius_value", operator, value)]

    @api.constrains("sendcloud_locations_radius_value")
    def _check_radius_value(self):
        uom_meter = self.env.ref("uom.product_uom_meter")
        for delivery in self:
            distance_meters = (
                delivery.sendcloud_locations_radius_unit._get_quantity_in_unit(
                    delivery.sendcloud_locations_radius_value, uom_meter
                )
            )

            if distance_meters > 50000:
                _debug.logic(
                    "sendcloud_radius_refused",
                    reason="too_large",
                    carrier=delivery.id,
                    meters=distance_meters,
                )
                max_distance = uom_meter._get_quantity_in_unit(
                    50000, delivery.sendcloud_locations_radius_unit
                )
                raise ValidationError(
                    self.env._(
                        "The maximum radius allowed is %(distance)d%(unit)s",
                        distance=max_distance,
                        unit=delivery.sendcloud_locations_radius_unit.name,
                    )
                )

            if distance_meters < 100:
                _debug.logic(
                    "sendcloud_radius_refused",
                    reason="too_small",
                    carrier=delivery.id,
                    meters=distance_meters,
                )
                min_distance = uom_meter._get_quantity_in_unit(
                    100, delivery.sendcloud_locations_radius_unit
                )
                raise ValidationError(
                    self.env._(
                        "The minimum radius allowed is %(distance)d%(unit)s",
                        distance=min_distance,
                        unit=delivery.sendcloud_locations_radius_unit.name,
                    )
                )

    def _sendcloud_get_close_locations(self, partner_address) -> list:
        superself = self.sudo()
        distance = int(
            self.sendcloud_locations_radius_unit._get_quantity_in_unit(
                self.sendcloud_locations_radius_value,
                self.env.ref("uom.product_uom_meter"),
            )
        )
        slr = SendcloudLocationsRequest(
            superself,
            superself.sendcloud_public_key,
            superself.sendcloud_secret_key,
            self.log_xml,
        )

        locations = slr.get_close_locations(
            partner_address, distance, self.sendcloud_shipping_id.carrier
        )

        return [
            {
                "id": location["id"],
                "name": location["name"].title(),
                "opening_hours": location["formatted_opening_times"],
                "street": f"{location['street'].title()} {location['house_number']}",
                "city": location["city"].title(),
                "zip_code": location["postal_code"],
                "country_code": location["country"],
                "latitude": location["latitude"],
                "longitude": location["longitude"],
            }
            for location in locations
        ]

import logging
from datetime import UTC, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BRAND = "AgroMarin"
DEFAULT_TZ = "UTC"
DELAY_PARAM = "stock_fleet_route.delay_threshold_minutes"
DEFAULT_DELAY_MINUTES = 15
# A GPS reading older than this does not say where the vehicle is now.
GPS_FRESH = timedelta(minutes=30)
# A stop reached after this local hour does not make it within the working day.
DAY_END_HOUR = 19


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    route_total_minutes = fields.Integer(
        string="Route Duration (min)",
        copy=False,
        readonly=True,
        help="From departure back to the warehouse, with traffic and the service "
        "time at every stop.",
    )
    route_distance_km = fields.Float(
        string="Route Distance (km)",
        digits=(16, 1),
        copy=False,
        readonly=True,
    )
    route_computed_at = fields.Datetime(
        string="Route Computed",
        copy=False,
        readonly=True,
        help="When the stop order or the arrival times were last computed.",
    )
    route_warning = fields.Text(
        copy=False,
        readonly=True,
        help="What the suggested route could not solve: customers without "
        "coordinates, stops reached too late in the day.",
    )

    def _route_privileged(self):
        return self.with_privilege(
            "stock_fleet_route.privilege_trip_route",
            reason="a trip plans its route and tells its crew and sellers",
        )

    def _route_warehouse(self):
        self.check_singleton()
        return self.picking_type_id.warehouse_id

    def _route_origin(self):
        warehouse = self._route_warehouse()
        origin = warehouse and warehouse._trip_origin()
        if not origin:
            raise UserError(
                self.env._(
                    "Set the trip origin coordinates on warehouse %s, or the "
                    "coordinates of its address.",
                    warehouse.display_name,
                )
            )
        return origin

    def _route_service(self):
        return timedelta(minutes=self._route_warehouse().route_service_minutes)

    def _route_tz(self):
        self.check_singleton()
        return ZoneInfo(
            self._route_warehouse().partner_id.tz
            or self.company_id.partner_id.tz
            or DEFAULT_TZ
        )

    def _route_local(self, date):
        """``date`` (naive UTC) in the warehouse's time zone."""
        return date.replace(tzinfo=UTC).astimezone(self._route_tz())

    def _route_hour(self, date):
        return self._route_local(date).strftime("%H:%M")

    def _route_etas(self, pickings, legs, start):
        """Arrival at each of ``pickings``, visited in order from ``start``.

        :return: {picking: arrival (naive UTC)}
        :rtype: dict
        """
        service = self._route_service()
        etas = {}
        clock = start
        for picking, leg in zip(pickings, legs, strict=False):
            clock += timedelta(seconds=leg["seconds"])
            etas[picking] = clock
            clock += service
        return etas

    # ------------------------------------------------------------------
    # Suggested route
    # ------------------------------------------------------------------
    def _route_start(self):
        now = fields.Datetime.now()
        if self.date_departure:
            return self.date_departure
        return max(self.date_planned, now) if self.date_planned else now

    def action_route_suggest(self) -> None:
        """Order the stops by TomTom's best route and estimate the arrivals."""
        self.check_singleton()
        if self.trip_state not in ("planned", "loaded"):
            raise UserError(
                self.env._(
                    "Trip %s has already left: its route can only be refreshed.",
                    self.name,
                )
            )
        origin = self._route_origin()
        stops = self.picking_ids.filtered(lambda p: p.state != "cancel").sorted(
            lambda p: (p.batch_sequence, p.id)
        )
        located = stops.filtered(lambda p: p._trip_location())
        missing = stops - located
        start = self._route_start()
        ordered = located.browse()
        legs = []
        if located:
            depart_at = "now"
            if start > fields.Datetime.now() + timedelta(minutes=1):
                depart_at = start.strftime("%Y-%m-%dT%H:%M:%SZ")
            route = self.env["stock.fleet.route.tomtom"]._calculate_route(
                [origin, *(p._trip_location() for p in located), origin],
                best_order=True,
                depart_at=depart_at,
                company=self.company_id,
            )
            ordered = located.browse([located[i].id for i in route["order"]])
            legs = route["legs"]
        for sequence, picking in enumerate(ordered | missing, start=1):
            picking.batch_sequence = sequence
        etas = self._route_etas(ordered, legs, start)
        for picking, eta in etas.items():
            picking.write({"trip_eta": eta, "trip_eta_notified": eta})
        missing.write({"trip_eta": False, "trip_eta_notified": False})
        self.write(
            {
                "route_total_minutes": round(
                    (
                        sum(leg["seconds"] for leg in legs)
                        + self._route_service().total_seconds() * len(ordered)
                    )
                    / 60
                ),
                "route_distance_km": sum(leg["meters"] for leg in legs) / 1000,
                "route_computed_at": fields.Datetime.now(),
                "route_warning": self._route_suggest_warning(missing, etas, start),
            }
        )

    def _route_suggest_warning(self, missing, etas, start) -> str:
        warnings = []
        if missing:
            warnings.append(
                self.env._(
                    "Customers without coordinates, left at the end: %s.",
                    ", ".join(
                        f"{p.partner_id.display_name} ({p.name})" for p in missing
                    ),
                )
            )
        start_day = self._route_local(start).date()
        late = [
            picking
            for picking, eta in etas.items()
            if self._route_local(eta).date() > start_day
            or self._route_local(eta).hour >= DAY_END_HOUR
        ]
        if late:
            warnings.append(
                self.env._(
                    "Does not make it within the day: %(customers)s arrive after "
                    "%(hour)s:00.",
                    customers=", ".join(p.partner_id.display_name for p in late),
                    hour=DAY_END_HOUR,
                )
            )
        return "\n".join(warnings)

    # ------------------------------------------------------------------
    # Google Maps
    # ------------------------------------------------------------------
    def _route_google_maps_url(self):
        """Directions through the stops in trip order; once the trip left, from
        wherever the phone is and through the stops still pending."""
        self.check_singleton()
        stops = self.picking_ids.filtered(lambda p: p.state != "cancel")
        if self.date_departure:
            stops = stops.filtered(lambda p: p.state != "done")
        points = [
            p._trip_location()
            for p in stops.sorted("batch_sequence")
            if p._trip_location()
        ]
        if not points:
            return ""

        def fmt(point):
            return f"{point[0]},{point[1]}"

        params = {"api": "1"}
        warehouse = self._route_warehouse()
        origin = warehouse and warehouse._trip_origin()
        if origin and not self.date_departure:
            params["origin"] = fmt(origin)
        params["destination"] = fmt(points[-1])
        if len(points) > 1:
            params["waypoints"] = "|".join(fmt(p) for p in points[:-1])
        params["travelmode"] = "driving"
        return "https://www.google.com/maps/dir/?" + urlencode(params, safe=",|")

    def action_route_google_maps(self) -> dict:
        url = self._route_google_maps_url()
        if not url:
            raise UserError(
                self.env._("No stop of trip %s has coordinates.", self.name)
            )
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------
    def _route_telegram(self, partner, text):
        """Send ``text`` to the Telegram chat linked to ``partner``, if any."""
        if not partner:
            return False
        chat = self.env["telegram.chat"]._for_partner(partner)[:1]
        if not chat:
            _logger.info("No Telegram chat for partner %s", partner.id)
            return False
        return chat.bot_id.send_message(chat.chat_id, text, parse_mode=None)

    def _route_tell_seller(self, picking, text, customer_text):
        """Tell the seller of ``picking`` ``text``, with a WhatsApp link that
        sends ``customer_text`` to the customer."""
        seller = picking._route_seller()
        if not seller:
            return False
        env = self.with_context(lang=seller.lang or self.env.lang).env
        url = picking._route_whatsapp_url(customer_text)
        if url:
            text += "\n" + env._("Let the customer know on WhatsApp: %s", url)
        else:
            text += "\n" + env._(
                "%s has no phone number on file: let them know another way.",
                picking.partner_id.display_name,
            )
        return self._route_telegram(seller.partner_id, text)

    # ------------------------------------------------------------------
    # Departure notice
    # ------------------------------------------------------------------
    def action_depart(self):
        res = super().action_depart()
        self._route_privileged()._route_notify_departure()
        return res

    def _route_notify_departure(self) -> None:
        self.check_singleton()
        for picking in self.picking_ids.filtered(
            lambda p: p.sale_id and p.state not in ("done", "cancel")
        ):
            seller = picking._route_seller()
            if not seller:
                continue
            env = self.with_context(lang=seller.lang or self.env.lang).env
            hour = self._route_hour(picking.trip_eta) if picking.trip_eta else None
            text = env._(
                "Trip %(trip)s left with %(picking)s for %(customer)s (%(order)s). "
                "Estimated arrival: %(hour)s.",
                trip=self.name,
                picking=picking.name,
                customer=picking.partner_id.display_name,
                order=picking.sale_id.name,
                hour=hour or env._("today"),
            )
            customer_text = (
                f"Tu pedido {BRAND} ya está en camino. "
                f"Hora estimada de llegada: {hour or 'hoy'}."
            )
            self._route_tell_seller(picking, text, customer_text)

    # ------------------------------------------------------------------
    # Live arrival times
    # ------------------------------------------------------------------
    @api.model
    def _cron_route_refresh_eta(self) -> None:
        trips = self.search(
            [
                ("trip_state", "=", "in_transit"),
                ("vehicle_id.gps_device_id", "!=", False),
            ]
        )
        for trip in trips:
            try:
                with self.env.cr.savepoint():
                    trip._route_privileged()._route_refresh_eta()
            except Exception:
                _logger.exception(
                    "Refreshing the arrival times of trip %s failed", trip.id
                )

    def action_route_refresh_eta(self) -> None:
        """Recompute the arrivals from where the vehicle is now."""
        self.check_singleton()
        if not self._route_privileged()._route_refresh_eta():
            raise UserError(
                self.env._(
                    "The vehicle of trip %s sent no GPS position in the last 30 "
                    "minutes.",
                    self.name,
                )
            )

    def _route_vehicle_position(self):
        """(latitude, longitude) of the vehicle from a recent GPS reading, or None."""
        self.check_singleton()
        log = self.vehicle_id.resource_id._gps_position(max_age=GPS_FRESH)
        return (log.latitude, log.longitude) if log else None

    def _route_refresh_eta(self) -> bool:
        """Estimate the pending arrivals from the vehicle's position, keeping the
        stop order, and report the delays above the threshold.

        :return: False when the vehicle has no recent position
        :rtype: bool
        """
        self.check_singleton()
        position = self._route_vehicle_position()
        if not position:
            return False
        pending = self.picking_ids.filtered(
            lambda p: (
                p.state not in ("done", "cancel")
                and not p.trip_arrival_date
                and p._trip_location()
            )
        ).sorted("batch_sequence")
        if pending:
            route = self.env["stock.fleet.route.tomtom"]._calculate_route(
                [position, *(p._trip_location() for p in pending)],
                company=self.company_id,
            )
            threshold = self.env["ir.config_parameter"].get_param_int(
                DELAY_PARAM, DEFAULT_DELAY_MINUTES
            )
            etas = self._route_etas(pending, route["legs"], fields.Datetime.now())
            for picking, eta in etas.items():
                vals = {"trip_eta": eta}
                baseline = picking.trip_eta_notified
                late = round((eta - baseline).total_seconds() / 60) if baseline else 0
                if not baseline or late >= threshold:
                    vals["trip_eta_notified"] = eta
                if baseline and late >= threshold:
                    self._route_notify_delay(picking, eta, late)
                picking.write(vals)
        self.route_computed_at = fields.Datetime.now()
        return True

    def _route_notify_delay(self, picking, eta, minutes) -> None:
        """Tell the crew and the seller that ``picking`` arrives ``minutes`` late."""
        hour = self._route_hour(eta)
        seller = picking._route_seller()
        crew = (
            self.supervisor_id.partner_id | self.operator_id.user_id.partner_id
        ) - seller.partner_id
        for partner in crew:
            env = self.with_context(lang=partner.lang or self.env.lang).env
            self._route_telegram(
                partner,
                env._(
                    "Delay on %(trip)s: %(customer)s arrives at %(hour)s "
                    "(+%(minutes)s min).",
                    trip=self.name,
                    customer=picking.partner_id.display_name,
                    hour=hour,
                    minutes=minutes,
                ),
            )
        if seller:
            env = self.with_context(lang=seller.lang or self.env.lang).env
            self._route_tell_seller(
                picking,
                env._(
                    "Delay on %(trip)s: %(customer)s (%(picking)s) now arrives at "
                    "%(hour)s (+%(minutes)s min).",
                    trip=self.name,
                    customer=picking.partner_id.display_name,
                    picking=picking.name,
                    hour=hour,
                    minutes=minutes,
                ),
                f"Estamos detenidos por tráfico, tu pedido {BRAND} llegará "
                f"aproximadamente {minutes} minutos más tarde ({hour}).",
            )

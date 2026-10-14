from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import SQL

from odoo.addons.telegram.tools import format as tg

DEPARTURE_ALERTS = (
    "departure_without_trip",
    "departure_not_loaded",
    "departure_blocked",
    "departure_without_route",
)
POSITION_MAX_AGE = timedelta(hours=1)


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    @api.model
    def _get_exit_gps_odometer(self, vehicle) -> float:
        if not vehicle or not vehicle.resource_id._gps_device_ids():
            return super()._get_exit_gps_odometer(vehicle)
        return vehicle.resource_id._get_current_gps_odometer()

    @api.model
    def _get_exit_gps_place(self, vehicle) -> str | None:
        if not vehicle or not vehicle.resource_id._gps_device_ids():
            return super()._get_exit_gps_place(vehicle)
        resource = vehicle.resource_id.with_privilege(
            "stock_fleet_exit_gps.privilege_exit_gps_read",
            reason="a route names the place its vehicle stays",
        )
        position = resource._gps_position(max_age=POSITION_MAX_AGE)
        if not position:
            return super()._get_exit_gps_place(vehicle)
        self.env["device.geo.fence"].flush_model(["the_geom", "active"])
        self.env.cr.execute(
            SQL(
                """
                SELECT id FROM device_geo_fence
                 WHERE active AND the_geom IS NOT NULL
                   AND ST_Covers(
                        the_geom,
                        ST_Transform(
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                            ST_SRID(the_geom)
                        )
                   )
                 ORDER BY ST_Area(the_geom), id
                 LIMIT 1
                """,
                position.longitude,
                position.latitude,
            )
        )
        row = self.env.cr.fetchone()
        if not row:
            return super()._get_exit_gps_place(vehicle)
        return (
            self.env["device.geo.fence"]
            .with_privilege(
                "stock_fleet_exit_gps.privilege_exit_gps_read",
                reason="a route names the place its vehicle stays",
            )
            .browse(row[0])
            .name
        )

    def _trip_gps_on_exit(self, vehicle, log, warehouse) -> None:
        Alert = self.env["stock.trip.alert"]
        alert_domain = Domain("vehicle_id", "=", vehicle.id) & Domain(
            "date", "=", log.timestamp
        )
        before = Alert.search(alert_domain)
        super()._trip_gps_on_exit(vehicle, log, warehouse)
        if not warehouse.fleet_exit_log or self.search_count(
            [("vehicle_id", "=", vehicle.id), ("trip_state", "=", "in_transit")],
            limit=1,
        ):
            return
        if before.filtered(lambda alert: alert.alert_type in DEPARTURE_ALERTS):
            return
        waiting = self.search(
            [
                ("vehicle_id", "=", vehicle.id),
                ("is_fleet_exit", "=", True),
                ("exit_requested_uid", "!=", False),
                ("date_departure", "=", False),
                ("state", "!=", "cancel"),
            ],
            limit=1,
        )
        if not Alert.search_count(
            alert_domain & Domain("alert_type", "in", DEPARTURE_ALERTS), limit=1
        ):
            waiting._trip_alert(
                vehicle,
                "departure_without_route",
                log.timestamp,
                latitude=log.latitude,
                longitude=log.longitude,
                note=waiting.name or warehouse.name,
            )
        self._notify_authorisers(
            lambda translated: translated._get_exit_alert_text(
                vehicle, log, warehouse, waiting
            ),
            warehouse.company_id,
        )

    def _get_exit_alert_text(self, vehicle, log, warehouse, waiting) -> str:
        moment = fields.Datetime.context_timestamp(
            self.with_context(tz=vehicle.resource_id.tz), log.timestamp
        )
        lines = [
            self.env._(
                "⚠️ %(vehicle)s left %(warehouse)s at %(time)s without an "
                "authorised route."
            )
            % {
                "vehicle": tg.bold(vehicle.display_name),
                "warehouse": tg.escape(warehouse.name),
                "time": moment.strftime("%H:%M"),
            }
        ]
        if waiting:
            lines.append(
                self.env._(
                    "%(route)s, asked by %(driver)s for %(activities)s, is still "
                    "waiting for authorisation."
                )
                % {
                    "route": tg.bold(waiting.name),
                    "driver": tg.escape(waiting.operator_id.name),
                    "activities": tg.escape(waiting.exit_activity_summary or "—"),
                }
            )
        operator = vehicle.operator_employee_id
        if operator:
            lines.append(
                self.env._("Its operator: %(operator)s.")
                % {"operator": tg.escape(operator.name)}
            )
        if log.latitude or log.longitude:
            lines.append(
                tg.link(
                    self.env._("See it on the map"),
                    f"https://maps.google.com/?q={log.latitude},{log.longitude}",
                )
            )
        return "\n".join(lines)

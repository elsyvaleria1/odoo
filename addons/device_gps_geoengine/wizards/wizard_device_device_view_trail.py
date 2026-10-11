import logging
from datetime import UTC

from shapely.geometry import LineString

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.colors import GPS_TRAIL_COLORS, get_palette_color
from odoo.libs.json import dumps as json_dumps

from odoo.addons.geoengine.models.fields import fit_line_vertices, max_geometry_size

_logger = logging.getLogger(__name__)


class WizardDeviceDeviceViewTrail(models.TransientModel):
    _name = "wizard.device.device.view.trail"
    _description = "GPS Trail Wizard"

    selection_mode = fields.Selection(
        selection=[
            ("device", "By GPS Device"),
        ],
        default="device",
        required=True,
        help="Choose how to select GPS tracking sources",
    )

    device_ids = fields.Many2many(
        comodel_name="device.device",
        relation="gps_trail_wizard_device_rel",
        column1="wizard_id",
        column2="device_id",
        domain="[('is_gps_device', '=', True)]",
        help="Select GPS devices directly (advanced)",
    )

    date_from = fields.Datetime(
        default=lambda self: self._default_date_from(),
        required=True,
        help="Start date/time for trail generation (in your timezone)",
    )
    date_to = fields.Datetime(
        default=lambda self: self._default_date_to(),
        required=True,
        help="End date/time for trail generation (in your timezone)",
    )

    @api.model
    def _default_date_from(self):
        now_user_tz = fields.Datetime.context_timestamp(
            self.env.user,
            fields.Datetime.now(),
        )
        start_of_day = now_user_tz.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_of_day.astimezone(UTC).replace(tzinfo=None)

    @api.model
    def _default_date_to(self):
        now_user_tz = fields.Datetime.context_timestamp(
            self.env.user,
            fields.Datetime.now(),
        )
        end_of_day = now_user_tz.replace(hour=23, minute=59, second=59, microsecond=0)
        return end_of_day.astimezone(UTC).replace(tzinfo=None)

    group_by = fields.Selection(
        selection=[
            ("source", "One Trail per Selection"),
            ("day", "Group by Day"),
            ("single", "Single Combined Trail"),
        ],
        default="source",
        required=True,
        help="How to group GPS points into trails",
    )

    trail_color = fields.Char(
        default="#3366FF",
        help="Hex color for trail lines",
    )

    resolved_device_ids = fields.Many2many(
        comodel_name="device.device",
        relation="gps_trail_wizard_resolved_device_rel",
        column1="wizard_id",
        column2="device_id",
        compute="_compute_resolved_devices",
        store=False,
        help="GPS devices resolved from selection (computed)",
    )
    selection_summary = fields.Text(
        compute="_compute_selection_summary",
        help="Human-readable summary of current selection",
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self) -> None:
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(self.env._("Start date must be before end date"))

    @api.depends("selection_mode", "device_ids")
    def _compute_resolved_devices(self) -> None:
        for wizard in self:
            wizard.resolved_device_ids = wizard.device_ids

    @api.depends("selection_mode", "device_ids")
    def _compute_selection_summary(self) -> None:
        for wizard in self:
            count = len(wizard.device_ids)
            if count == 0:
                wizard.selection_summary = self.env._("No devices selected")
            elif count == 1:
                wizard.selection_summary = wizard.device_ids[0].name
            else:
                wizard.selection_summary = self.env._("%d devices selected") % count

    @api.onchange("selection_mode")
    def _onchange_selection_mode(self) -> None:
        self.device_ids = False

    def _gps_trail_domain(self):
        return Domain(self.env.context.get("gps_observation_domain", []))

    def action_generate_trails(self):
        self.check_singleton()
        self.check_access("read")

        if not self.resolved_device_ids:
            raise UserError(self._empty_selection_message())

        source_mapping = self._prepare_source_mapping()

        gps_log_model = self.env["device.data.log.gps"]
        gps_log_limit = 50000
        logs = gps_log_model.trail_points(
            self.resolved_device_ids.ids,
            self.date_from,
            self.date_to,
            limit=gps_log_limit,
            observation_domain=list(self._gps_trail_domain()),
        )
        if len(logs) == gps_log_limit:
            _logger.warning(
                "GPS trail query hit the %d-record cap. Trails may be incomplete. "
                "Narrow the date range or reduce the number of selected devices.",
                gps_log_limit,
            )

        if not logs:
            raise UserError(
                self.env._(
                    "No GPS data found for the selection in the specified date range"
                ),
            )

        _logger.info(
            "Generating trails for %d devices with %d GPS points",
            len(self.resolved_device_ids),
            len(logs),
        )

        logs, source_mapping = self._prepare_trail_logs(logs, source_mapping)
        trails = self._generate_trails(logs, source_mapping)

        if not trails:
            raise UserError(
                self.env._(
                    "Could not generate any trails from the GPS data. This can happen when devices are stationary."
                ),
            )

        result_ids = (
            self.env["wizard.device.device.view.trail.result"].create(trails).ids
        )

        date_from_str = self.date_from.strftime("%Y-%m-%d %H:%M")
        date_to_str = self.date_to.strftime("%Y-%m-%d %H:%M")

        result_context = {
            "gps_trail_date_from": date_from_str,
            "gps_trail_date_to": date_to_str,
            "gps_trail_selection_mode": dict(
                self._fields["selection_mode"].selection
            ).get(
                self.selection_mode,
                self.selection_mode,
            ),
            "gps_trail_selection_summary": self.selection_summary or "",
            "gps_trail_group_by": dict(self._fields["group_by"].selection).get(
                self.group_by,
                self.group_by,
            ),
            "gps_trail_count": len(result_ids),
        }

        title_parts = [self.env._("GPS Trails")]
        if self.selection_summary:
            title_parts.append(self.selection_summary)
        title_parts.append(f"{date_from_str} → {date_to_str}")

        return {
            "name": " - ".join(title_parts),
            "type": "ir.actions.act_window",
            "res_model": "wizard.device.device.view.trail.result",
            "view_mode": "geoengine,list,form",
            "views": [[False, "geoengine"], [False, "list"], [False, "form"]],
            "domain": [("id", "in", result_ids)],
            "context": result_context,
        }

    def _prepare_source_mapping(self):
        mapping = {}
        devices = self.resolved_device_ids
        use_auto_colors = len(devices) > 1

        for idx, device in enumerate(devices):
            if use_auto_colors:
                color = get_palette_color(idx, GPS_TRAIL_COLORS, wrap=True)
            else:
                color = self.trail_color

            mapping[device.id] = {
                "device_id": device.id,
                "device_name": device.name,
                "color": color,
                **self._trail_source_extras(device),
            }

        return mapping

    def _empty_selection_message(self):
        self.check_singleton()
        return self.env._("Please select at least one GPS device")

    def _trail_source_extras(self, device):
        return {}

    def _trail_result_vals(self, source_info):
        return {}

    def _get_trail_display_name(self, source_info, suffix=""):
        parts = []

        if source_info.get("operator_name"):
            parts.append(source_info["operator_name"])

        if source_info.get("asset_name"):
            asset_part = source_info["asset_name"]
            if source_info.get("license_plate"):
                asset_part = f"{asset_part} ({source_info['license_plate']})"
            parts.append(asset_part)

        if not parts:
            parts.append(source_info.get("device_name", "Unknown"))

        name = " - ".join(parts)

        if suffix:
            name = f"{name} [{suffix}]"

        return name

    def _prepare_trail_logs(self, logs, source_mapping):
        return logs, source_mapping

    def _generate_trails(self, logs, source_mapping):
        if self.group_by == "source":
            return self._generate_trails_by_source(logs, source_mapping)
        if self.group_by == "day":
            return self._generate_trails_by_day(logs, source_mapping)
        return self._generate_single_trail(logs, source_mapping)

    def _generate_trails_by_source(self, logs, source_mapping):
        by_device = {}
        for log in logs:
            by_device.setdefault(log.get("source_key", log["device_id"]), []).append(
                log
            )

        trails = []
        for source_key, device_logs in by_device.items():
            device_id = device_logs[0]["device_id"]
            source_info = source_mapping.get(source_key, {})
            if vals := self._trail_vals(
                device_logs,
                self._get_trail_display_name(source_info),
                device_id,
                source_info,
                source_info.get("color", self.trail_color),
            ):
                trails.append(vals)
        return trails

    def _generate_trails_by_day(self, logs, source_mapping):
        by_day_device = {}
        for log in logs:
            key = (log["timestamp"].date(), log.get("source_key", log["device_id"]))
            by_day_device.setdefault(key, []).append(log)

        trails = []
        for (day, source_key), day_logs in by_day_device.items():
            device_id = day_logs[0]["device_id"]
            source_info = source_mapping.get(source_key, {})
            if vals := self._trail_vals(
                day_logs,
                self._get_trail_display_name(source_info, suffix=str(day)),
                device_id,
                source_info,
                source_info.get("color", self.trail_color),
            ):
                trails.append(vals)
        return trails

    def _generate_single_trail(self, logs, source_mapping) -> list:
        device_count = len(source_mapping)
        if device_count == 1:
            source_info = next(iter(source_mapping.values()))
            name = self._get_trail_display_name(source_info, suffix="Combined")
        else:
            names = []
            for info in list(source_mapping.values())[:3]:
                if info.get("operator_name"):
                    names.append(info["operator_name"])
                elif info.get("asset_name"):
                    names.append(info["asset_name"])
                else:
                    names.append(info.get("device_name", "Unknown"))

            name = ", ".join(names)
            if device_count > 3:
                name += f" (+{device_count - 3})"
            name = f"Combined: {name}"

        vals = self._trail_vals(logs, name, False, {}, self.trail_color)
        return [vals] if vals else []

    def _trail_vals(self, logs, name, device_id, source_info, color) -> dict | None:
        coords, timestamps = self._extract_coordinates_with_timestamps(logs)
        if len(coords) < 2:
            return None
        if (kept := fit_line_vertices(coords, max_geometry_size(self.env))) is None:
            raise UserError(
                self.env._(
                    "A trail of %(count)d positions is too large to draw, even "
                    "simplified. Narrow the dates, or group the trail by day.",
                    count=len(coords),
                )
            )
        return {
            "name": name,
            "the_trail": LineString([coords[index] for index in kept]).wkt,
            "trail_timestamps": json_dumps([timestamps[index] for index in kept]),
            "device_id": device_id,
            **self._trail_result_vals(source_info),
            "point_count": len(coords),
            "date_from": logs[0]["timestamp"],
            "date_to": logs[-1]["timestamp"],
            "trail_color": color,
            **self._get_trail_analytics(logs),
        }

    def _extract_coordinates_with_timestamps(self, logs):
        return self.env["device.data.log.gps"].trail_coordinates(logs)

    def _get_trail_analytics(self, logs):
        device_ids = {row["device_id"] for row in logs if row.get("device_id")}
        tanks = {
            device.id: device.fuel_tank_capacity
            for device in self.env["device.device"].browse(sorted(device_ids))
        }
        return self.env["device.data.log.gps"].trail_analytics(logs, tanks)

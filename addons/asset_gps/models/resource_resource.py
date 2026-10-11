import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

ODOMETER_LOOKBACK_PARAM = "asset_gps.odometer_lookback_days"
DEFAULT_ODOMETER_LOOKBACK_DAYS = 30


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    @api.model
    def _gps_odometer_lookback_days(self):
        raw = self.env.registry.settings.get(
            self.env, ODOMETER_LOOKBACK_PARAM, DEFAULT_ODOMETER_LOOKBACK_DAYS
        )
        try:
            days = int(raw)
        except TypeError, ValueError:
            days = 0
        if days <= 0:
            _logger.warning(
                "%s is %r, which is not a positive number of days; using %d.",
                ODOMETER_LOOKBACK_PARAM,
                raw,
                DEFAULT_ODOMETER_LOOKBACK_DAYS,
            )
            return DEFAULT_ODOMETER_LOOKBACK_DAYS
        return days

    @api.model
    def _gps_odometer_today(self, company):
        tz = company.partner_id.tz or "UTC"
        return fields.Date.context_today(self.with_context(tz=tz))

    @api.model
    def _gps_odometer_split_ledgers(self, assets):
        split = self.browse()
        for asset, companies in (
            self.env["resource.log"]
            .sudo()
            ._read_group(
                [("asset_id", "in", assets.ids)],
                ["asset_id"],
                ["company_id:array_agg"],
            )
        ):
            if len({company for company in companies if company}) > 1:
                split |= asset
        return split

    @api.model
    def _cron_record_gps_odometer(self):
        tracked = self.search(
            [("gps_device_id", "!=", False), ("kind_id", "!=", False)]
        )
        if not tracked:
            return
        split = self._gps_odometer_split_ledgers(tracked)
        if split:
            _logger.warning(
                "GPS odometer snapshot: skipping %d asset(s) whose ledger already "
                "spans companies, which no snapshot can repair. Move their logs "
                "into one company: %s",
                len(split),
                ", ".join(split.mapped("display_name")),
            )
            tracked -= split
            if not tracked:
                return
        log_model = self.env["resource.log"]
        today_by_asset = {asset.id: asset._get_local_date() for asset in tracked}
        todays_log = {
            (log.asset_id.id, log.date): log
            for log in log_model.search(
                [
                    ("asset_id", "in", tracked.ids),
                    ("source", "=", "gps"),
                    ("date", "in", list(set(today_by_asset.values()))),
                ]
            )
        }
        vals_list = []
        advanced = 0
        for asset in tracked:
            today = today_by_asset[asset.id]
            reading = asset._get_current_gps_odometer()
            if reading <= 0 or reading <= asset.odometer:
                continue
            log = todays_log.get((asset.id, today))
            if log:
                log.odometer = reading
                advanced += 1
                continue
            vals_list.append(
                {
                    "asset_id": asset.id,
                    "date": today,
                    "odometer": reading,
                    "source": "gps",
                    "state": "done",
                    "notes": self.env._(
                        "Odometer snapshot from %(device)s.",
                        device=asset.gps_device_id.display_name,
                    ),
                }
            )
        if vals_list:
            log_model.create(vals_list)
        _logger.info(
            "GPS odometer snapshot: %d of %d tracked assets advanced.",
            len(vals_list) + advanced,
            len(tracked),
        )

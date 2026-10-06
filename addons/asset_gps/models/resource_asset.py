import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

ODOMETER_LOOKBACK_PARAM = "asset_gps.odometer_lookback_days"
DEFAULT_ODOMETER_LOOKBACK_DAYS = 30


class ResourceAsset(models.Model):
    _inherit = "resource.asset"

    @api.model
    def _gps_odometer_lookback_days(self):
        """How old the last GPS reading may be and still count as current.

        Read defensively: the parameter is admin-editable from Settings, and a
        value that will not parse used to raise out of the nightly cron and
        abort its run for every asset.
        """
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
        """Compatibility helper for company-local dates.

        Automated snapshots use the resource's own ``_get_local_date`` instead.
        """
        tz = company.partner_id.tz or "UTC"
        return fields.Date.context_today(self.with_context(tz=tz))

    @api.model
    def _gps_odometer_split_ledgers(self, assets):
        """The assets whose stored ledger already spans more than one company.

        ``resource.asset.log._check_ledger_does_not_span_companies`` refuses any
        write touching one of these, and says so in as many words: the split
        predates the write and re-saving will not clear it. Nothing a snapshot
        can do repairs it.

        Naming them is what keeps that refusal proportionate. The snapshot books
        the whole fleet in one ``create()``, so the constraint firing for a single
        asset takes every other asset's reading down with it -- and an ``ir.cron``
        that raises is silent, so the fleet simply stops being measured. That is
        what happened for eight consecutive nights before anyone read the failure
        counter.

        sudo: the same reason the constraint uses it. Deciding whether a ledger is
        whole means counting companies the acting user may not read, and reading
        one short would call a split ledger sound.
        """
        split = self.browse()
        for asset, companies in (
            self.env["resource.asset.log"]
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
        tracked = self.search([("gps_device_id", "!=", False)])
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
        log_model = self.env["resource.asset.log"]
        # Snapshot dates belong to the resource's local day. Resources in the
        # same company may work in different timezones.
        today_by_asset = {
            asset.id: asset.resource_id._get_local_date() for asset in tracked
        }
        # One snapshot per asset per day, kept current: the cron runs every
        # few minutes, and a day's row follows the counter upward each time
        # the device has advanced, so the asset's odometer is live for
        # whoever asks for it (a dispatch, a maintenance trigger) without a
        # row per run.
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
                    # An automated snapshot has nothing left to approve; the
                    # default "new" would leave one permanent draft per tracked
                    # asset per day in the log kanban.
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

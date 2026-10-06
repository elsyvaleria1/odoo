from datetime import UTC, datetime, time, timedelta
from typing import Self
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.tools.date_utils import start_of

DASHBOARD_WINDOW_DAYS = 14

DASHBOARD_PERIODS = ("day", "week", "month", "window")

PICKER_HISTORY_DAYS = 400


def _truncate_to_hour(stamp):
    aware = stamp.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return aware.replace(tzinfo=None)


class DeviceMachineBucket(models.Model):
    _name = "device.machine.bucket"
    _description = "Remote Machine Hourly Bucket"
    _order = "bucket_start desc"

    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        required=True,
        domain="[('is_counter_device', '=', True)]",
        ondelete="restrict",
    )
    bucket_start = fields.Datetime(
        index=True,
        required=True,
    )
    bucket_end = fields.Datetime()
    count_start = fields.Integer(help="Counter value when the bucket opened.")
    count_end = fields.Integer(help="Last counter value seen in the bucket.")
    count_carried = fields.Integer(
        string="Carried Over Reset",
        help="Pieces already counted in this hour before the PLC reset its "
        "counter. Kept apart from count_start/count_end so those stay the "
        "literal values the PLC reported for the run in progress.",
    )
    delta = fields.Integer(
        help="Pieces produced in the bucket "
        "(count_end - count_start, plus anything carried over a reset)."
    )
    msg_count = fields.Integer(
        string="Pings While Producing",
        help="MQTT pings recorded once this hour started producing. The bucket "
        "opens on the first reading that moves the counter, so pings received "
        "earlier in the hour, while the machine was idle, are not counted. Use "
        "it as a sanity check: few pings against a large count means readings "
        "went missing.",
    )
    reset_detected = fields.Boolean(
        help="True if the PLC's weekly counter reset (Conteo=0) was observed."
    )

    _device_bucket_uniq = models.Constraint(
        "UNIQUE(device_id, bucket_start)",
        "A bucket already exists for this device and hour.",
    )
    _delta_not_negative = models.Constraint(
        "CHECK(delta >= 0)",
        "A bucket cannot report negative production.",
    )

    @api.model
    def _dashboard_timezone(self):
        return self.env.context.get("tz") or self.env.user.tz or "UTC"

    @api.model
    def _period_label(self, period, day_from=None, day_to=None):
        if day_from:
            start = fields.Date.to_date(day_from).strftime("%d/%m/%Y")
            end = fields.Date.to_date(day_to).strftime("%d/%m/%Y") if day_to else None
            return f"{start} – {end}" if end and end != start else start
        return {
            "day": self.env._("today"),
            "week": self.env._("this week"),
            "month": self.env._("this month"),
        }.get(period, self.env._("last %s days", DASHBOARD_WINDOW_DAYS))

    @api.model
    def _period_domain(self, period, tz_name, day_from=None, day_to=None) -> list:
        zone = ZoneInfo(tz_name)

        if day_from:
            start = datetime.combine(
                fields.Date.to_date(day_from), time.min, tzinfo=zone
            )
            last = fields.Date.to_date(day_to or day_from)
            end = datetime.combine(last, time.min, tzinfo=zone) + timedelta(days=1)
            return [
                ("bucket_start", ">=", fields.Datetime.to_datetime(start)),
                ("bucket_start", "<", fields.Datetime.to_datetime(end)),
            ]

        now = fields.Datetime.now().replace(tzinfo=UTC).astimezone(zone)
        if period in ("day", "week", "month"):
            start = start_of(now, period)
        else:
            start = now - timedelta(days=DASHBOARD_WINDOW_DAYS)
        return [("bucket_start", ">=", fields.Datetime.to_datetime(start))]

    @api.model
    def _dashboard_data(self, period="window", day_from=None, day_to=None) -> dict:
        if period not in DASHBOARD_PERIODS:
            period = "window"
        tz_name = self._dashboard_timezone()
        domain = self._period_domain(period, tz_name, day_from, day_to)

        records = self.with_context(tz=tz_name)

        devices = self.env["device.device"].search(
            [("is_counter_device", "=", True)], order="id"
        )
        per_day = {}
        pieces_by_device = {}
        for bucket_day, device, pieces in records._read_group(
            domain,
            ["bucket_start:day", "device_id"],
            ["delta:sum"],
            order="bucket_start:day",
        ):
            pieces = int(pieces or 0)
            per_day.setdefault(bucket_day, {})[device.display_name] = pieces
            pieces_by_device[device.id] = pieces_by_device.get(device.id, 0) + pieces

        machines = [
            {
                "id": device.id,
                "name": device.display_name,
                "bottles": pieces_by_device.get(device.id, 0),
            }
            for device in devices
        ]
        machines.sort(key=lambda machine: machine["bottles"], reverse=True)

        difference = None
        if len(machines) >= 2:
            difference = {
                "a": machines[0]["name"],
                "b": machines[1]["name"],
                "diff": machines[0]["bottles"] - machines[1]["bottles"],
            }

        labels = [bucket_day.strftime("%d/%m") for bucket_day in per_day]
        datasets = [
            {
                "label": machine["name"],
                "data": [
                    per_day[bucket_day].get(machine["name"], 0)
                    for bucket_day in per_day
                ],
            }
            for machine in machines
        ]
        active_hours = self.search_count(domain + [("delta", ">", 0)])
        total_pieces = sum(machine["bottles"] for machine in machines)

        return {
            "workorder": None,
            "period": period,
            "day_from": day_from or False,
            "day_to": day_to or False,
            "period_label": self._period_label(period, day_from, day_to),
            "productive_days": records._productive_days(),
            "machines": machines,
            "totals": {
                "machines": len(machines),
                "runs": active_hours,
                "bottles": total_pieces,
            },
            "difference": difference,
            "chart": {"labels": labels, "datasets": datasets},
            "hourly": records._hourly_profile(domain, machines),
            "rate": {
                "avg_active": round(total_pieces / active_hours, 1)
                if active_hours
                else 0.0,
            },
        }

    @api.model
    def _productive_days(self) -> list:
        window_start = fields.Datetime.now() - timedelta(days=PICKER_HISTORY_DAYS)
        return [
            bucket_day.strftime("%Y-%m-%d")
            for (bucket_day,) in self._read_group(
                [("bucket_start", ">=", window_start), ("delta", ">", 0)],
                ["bucket_start:day"],
                order="bucket_start:day",
            )
        ]

    @api.model
    def _hourly_profile(self, domain, machines) -> dict:
        per_hour = {}
        for hour, device, pieces in self._read_group(
            domain, ["bucket_start:hour_number", "device_id"], ["delta:sum"]
        ):
            per_hour.setdefault(int(hour), {})[device.display_name] = int(pieces or 0)

        if not per_hour:
            return {"labels": [], "datasets": [], "peak": None}

        hours = range(min(per_hour), max(per_hour) + 1)
        totals_by_hour = {hour: sum(per_hour.get(hour, {}).values()) for hour in hours}
        peak_hour = max(totals_by_hour, key=lambda hour: totals_by_hour[hour])

        return {
            "labels": [f"{hour:02d}:00" for hour in hours],
            "datasets": [
                {
                    "label": machine["name"],
                    "data": [
                        per_hour.get(hour, {}).get(machine["name"], 0) for hour in hours
                    ],
                }
                for machine in machines
            ],
            "peak": {
                "hour": f"{peak_hour:02d}:00",
                "pieces": totals_by_hour[peak_hour],
            },
        }

    @api.model
    def _open_bucket(self, device, bucket_start, timestamp, count) -> Self:
        baseline = device.last_count or 0
        if count <= baseline:
            return self.browse()

        seen_before = self.search_count([("device_id", "=", device.id)]) or self.env[
            "device.machine.reading"
        ].search_count([("device_id", "=", device.id)])
        if not seen_before:
            return self.browse()

        return self.create(
            {
                "device_id": device.id,
                "bucket_start": bucket_start,
                "bucket_end": timestamp.replace(tzinfo=None),
                "count_start": baseline,
                "count_end": count,
                "delta": count - baseline,
                "msg_count": 1,
            }
        )

    @api.model
    def _apply_reading(self, device, timestamp, count):
        bucket_start = _truncate_to_hour(timestamp)
        bucket = self.search(
            [("device_id", "=", device.id), ("bucket_start", "=", bucket_start)],
            limit=1,
        )
        if not bucket:
            return self._open_bucket(device, bucket_start, timestamp, count)

        vals = {
            "msg_count": bucket.msg_count + 1,
            "bucket_end": timestamp.replace(tzinfo=None),
        }
        if count == 0 and bucket.count_end > 0:
            vals["reset_detected"] = True
            vals["count_carried"] = bucket.delta
            vals["count_start"] = count
            vals["count_end"] = count
            vals["delta"] = bucket.delta
        else:
            count_end = max(count, bucket.count_end)
            vals["count_end"] = count_end
            vals["delta"] = bucket.count_carried + count_end - bucket.count_start
        bucket.write(vals)
        return bucket

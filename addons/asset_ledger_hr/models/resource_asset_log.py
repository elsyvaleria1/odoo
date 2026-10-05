from datetime import datetime, time
from zoneinfo import ZoneInfo

from odoo import api, fields, models

ROLE_BY_LOG_FIELD = {"operator_id": "operator", "asset_manager_id": "manager"}
EMPLOYEE_FIELD_BY_LOG_FIELD = {
    "operator_id": "operator_employee_id",
    "asset_manager_id": "manager_employee_id",
}


class ProductAssetLog(models.Model):
    _inherit = "resource.log"

    source = fields.Selection(
        selection_add=[("assignment", "Operator Assignment")],
        ondelete={"assignment": "set default"},
    )

    operator_id = fields.Many2one(
        comodel_name="hr.employee",
        index=True,
        readonly=True,
        check_company=True,
        help="Employee operating the asset when this log entry was created. "
        "Snapshot value; does not change when the asset's current operator changes.",
    )
    asset_manager_id = fields.Many2one(
        comodel_name="hr.employee",
        index=True,
        readonly=True,
        check_company=True,
        help="Employee managing the asset when this log entry was created. "
        "Snapshot value; does not change when the asset's current manager changes.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        # Work on copies: the snapshot below fills in keys the caller never wrote,
        # and handing those back on the caller's own dictionaries is observable.
        vals_list = [dict(vals) for vals in vals_list]
        timelines = {}
        for vals in vals_list:
            asset_id = vals.get("asset_id")
            if not asset_id:
                continue
            needs_operator = "operator_id" not in vals
            needs_manager = "asset_manager_id" not in vals
            if not (needs_operator or needs_manager):
                continue
            target = vals.get("date") or fields.Date.context_today(self)
            if needs_operator:
                vals["operator_id"] = self._get_employee_at_date(
                    asset_id, "operator_id", target, timelines
                )
            if needs_manager:
                vals["asset_manager_id"] = self._get_employee_at_date(
                    asset_id, "asset_manager_id", target, timelines
                )
        return super().create(vals_list)

    @api.model
    def _get_employee_at_date(self, asset_id, lot_field, target_date, cache):
        key = (asset_id, lot_field)
        timeline = cache.get(key)
        if timeline is None:
            timeline = self._get_employee_timeline(asset_id, lot_field)
            cache[key] = timeline
        target_dt = self._business_day_cutoff(target_date)
        before = [t for t in timeline if t["date"] <= target_dt]
        if before:
            return before[-1]["new"] or False
        after = [t for t in timeline if t["date"] > target_dt]
        if after:
            return after[0]["old"] or after[0]["new"] or False
        asset = self.env["resource.asset"].browse(asset_id)
        holder = asset[EMPLOYEE_FIELD_BY_LOG_FIELD[lot_field]]
        return holder.id or False

    @api.model
    def _business_day_cutoff(self, target_date):
        """Return the naive UTC instant that closes `target_date` for the user.

        A log's `date` is a business day in the user's timezone while
        `mail_message.date` is naive UTC, so comparing the two unconverted
        shifts the cut-off by the UTC offset: in America/Mexico_City a change
        made at 20:00 local is stored as 02:00 UTC the next day and the day it
        belongs to would miss it. Normalising the argument to a date first also
        keeps the answer independent of whether the caller passed a `date`, a
        `datetime` or an ISO string -- the web client sends strings and Python
        callers send dates, and the two used to disagree.
        """
        day = fields.Date.to_date(target_date) or fields.Date.context_today(self)
        zone = ZoneInfo(self.env.context.get("tz") or self.env.user.tz or "UTC")
        return (
            datetime.combine(day, time.max, tzinfo=zone)
            .astimezone(ZoneInfo("UTC"))
            .replace(tzinfo=None)
        )

    @api.model
    def _get_employee_timeline(self, asset_id, lot_field):
        """Every hand-over of `lot_field`'s role on the asset, oldest first, as
        {date, old, new} employee ids: one entry per assignment start and one
        per end that nothing follows."""
        role = ROLE_BY_LOG_FIELD.get(lot_field)
        asset = self.env["resource.asset"].browse(asset_id).sudo()
        if not role or not asset.resource_id:
            return []
        self.env.flush_all()
        rows = (
            self.env["resource.assignment"]
            .sudo()
            .search(
                [
                    ("resource_id", "=", asset.resource_id.id),
                    ("custody_role", "=", role),
                ],
                order="date_start asc, id asc",
            )
        )
        employee_by_resource = asset._employee_by_resource(rows.assignee_id)
        timeline = []
        current = 0
        for index, row in enumerate(rows):
            employee = employee_by_resource.get(row.assignee_id.id)
            new = employee.id if employee else 0
            timeline.append({"date": row.date_start, "old": current, "new": new})
            current = new
            following = rows[index + 1] if index + 1 < len(rows) else None
            if row.date_end and (not following or row.date_end < following.date_start):
                timeline.append({"date": row.date_end, "old": current, "new": 0})
                current = 0
        return timeline

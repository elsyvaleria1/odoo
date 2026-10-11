from collections import defaultdict
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
        vals_list = [dict(vals) for vals in vals_list]
        timelines = self._get_employee_timelines(
            {
                (vals["asset_id"], lot_field)
                for vals in vals_list
                if vals.get("asset_id")
                for lot_field in ROLE_BY_LOG_FIELD
                if lot_field not in vals
            }
        )
        for lot_field, holder_field in EMPLOYEE_FIELD_BY_LOG_FIELD.items():
            self.env["resource.resource"].browse(
                {
                    asset_id
                    for (asset_id, field), timeline in timelines.items()
                    if field == lot_field and not timeline
                }
            ).mapped(holder_field)
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
        asset = self.env["resource.resource"].browse(asset_id)
        holder = asset[EMPLOYEE_FIELD_BY_LOG_FIELD[lot_field]]
        return holder.id or False

    @api.model
    def _business_day_cutoff(self, target_date):
        day = fields.Date.to_date(target_date) or fields.Date.context_today(self)
        zone = ZoneInfo(self.env.context.get("tz") or self.env.user.tz or "UTC")
        return (
            datetime.combine(day, time.max, tzinfo=zone)
            .astimezone(ZoneInfo("UTC"))
            .replace(tzinfo=None)
        )

    @api.model
    def _get_employee_timeline(self, asset_id, lot_field):
        key = (asset_id, lot_field)
        return self._get_employee_timelines({key})[key]

    @api.model
    def _get_employee_timelines(self, keys) -> dict:
        timelines = {key: [] for key in keys}
        wanted = {
            (asset_id, ROLE_BY_LOG_FIELD[lot_field])
            for asset_id, lot_field in keys
            if asset_id and lot_field in ROLE_BY_LOG_FIELD
        }
        if not wanted:
            return timelines
        rows = (
            self.env["resource.assignment"]
            .sudo()
            .search(
                [
                    ("resource_id", "in", list({asset_id for asset_id, _r in wanted})),
                    ("custody_role", "in", list({role for _a, role in wanted})),
                ],
                order="date_start asc, id asc",
            )
        )
        employee_by_resource = (
            self.env["resource.resource"].sudo()._employee_by_resource(rows.assignee_id)
        )
        rows_by_key = defaultdict(list)
        for row in rows:
            rows_by_key[row.resource_id.id, row.custody_role].append(row)
        for key in timelines:
            if role := ROLE_BY_LOG_FIELD.get(key[1]):
                timelines[key] = self._timeline_from_rows(
                    rows_by_key[key[0], role], employee_by_resource
                )
        return timelines

    @api.model
    def _timeline_from_rows(self, rows, employee_by_resource) -> list:
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

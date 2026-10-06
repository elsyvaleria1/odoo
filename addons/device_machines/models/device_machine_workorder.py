from odoo import api, fields, models


class DeviceMachineWorkorder(models.Model):
    _name = "device.machine.workorder"
    _description = "Remote Machine Work Order Run"
    _order = "date_start desc"

    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        required=True,
        ondelete="cascade",
    )
    workorder_id = fields.Many2one(
        comodel_name="mrp.workorder",
        index=True,
        required=True,
        ondelete="cascade",
    )
    production_id = fields.Many2one(
        related="workorder_id.production_id",
    )
    workcenter_id = fields.Many2one(
        related="workorder_id.workcenter_id",
    )

    count_start = fields.Integer(help="PLC cumulative counter when the run opened.")
    count_end = fields.Integer(help="Last PLC cumulative counter seen in the run.")
    count_carried = fields.Integer(
        string="Carried Over Reset",
        help="Units already counted in this run before the PLC reset its "
        "counter, so count_start/count_end can stay literal PLC values.",
    )
    bottles = fields.Integer(
        compute="_compute_bottles",
        store=True,
        help="Units counted by the PLC during this work order.",
    )

    date_start = fields.Datetime(required=True)
    date_end = fields.Datetime()
    duration_min = fields.Float(
        compute="_compute_duration_min",
        help="Minutes from first to last PLC reading (uses now while open).",
    )
    bottles_per_hour = fields.Float(compute="_compute_rate")
    bottles_per_min = fields.Float(compute="_compute_rate")

    _device_workorder_uniq = models.Constraint(
        "UNIQUE(device_id, workorder_id)",
        "A PLC run already exists for this device and work order.",
    )

    @api.depends("count_start", "count_end", "count_carried")
    def _compute_bottles(self) -> None:
        for run in self:
            run.bottles = run.count_carried + max(run.count_end - run.count_start, 0)

    @api.depends("date_start", "date_end")
    def _compute_duration_min(self) -> None:
        now = fields.Datetime.now()
        for run in self:
            if not run.date_start:
                run.duration_min = 0.0
                continue
            ref = run.date_end or now
            run.duration_min = (ref - run.date_start).total_seconds() / 60.0

    @api.depends("bottles", "duration_min")
    def _compute_rate(self) -> None:
        for run in self:
            hours = run.duration_min / 60.0
            run.bottles_per_hour = run.bottles / hours if hours else 0.0
            run.bottles_per_min = (
                run.bottles / run.duration_min if run.duration_min else 0.0
            )

    @api.model
    def get_dashboard_data(
        self, workorder_id=None, period="window", day_from=None, day_to=None
    ):
        if not workorder_id:
            return self.env["device.machine.bucket"]._dashboard_data(
                period, day_from, day_to
            )

        domain = [("workorder_id", "=", workorder_id)]

        header = None
        workorder = self.env["mrp.workorder"].browse(workorder_id).exists()
        if workorder:
            header = {
                "name": workorder.display_name,
                "mo": workorder.production_id.name,
                "product": workorder.product_id.display_name,
                "workcenter": workorder.workcenter_id.display_name,
            }

        machines = [
            {
                "id": device.id,
                "name": device.display_name,
                "bottles": int(bottles or 0),
                "runs": count,
            }
            for device, bottles, count in self._read_group(
                domain, ["device_id"], ["bottles:sum", "__count"]
            )
        ]
        machines.sort(key=lambda m: m["bottles"], reverse=True)

        difference = None
        if len(machines) >= 2:
            difference = {
                "a": machines[0]["name"],
                "b": machines[1]["name"],
                "diff": machines[0]["bottles"] - machines[1]["bottles"],
            }

        per_mo = {}
        for production, device, bottles in self._read_group(
            domain + [("production_id", "!=", False)],
            ["production_id", "device_id"],
            ["bottles:sum"],
        ):
            per_mo.setdefault(production.name, {})[device.display_name] = int(
                bottles or 0
            )
        labels = list(per_mo.keys())
        datasets = [
            {
                "label": m["name"],
                "data": [per_mo[mo].get(m["name"], 0) for mo in labels],
            }
            for m in machines
        ]

        return {
            "workorder": header,
            "period": False,
            "day_from": False,
            "day_to": False,
            "period_label": False,
            "productive_days": [],
            "machines": machines,
            "totals": {
                "machines": len(machines),
                "runs": sum(m["runs"] for m in machines),
                "bottles": sum(m["bottles"] for m in machines),
            },
            "difference": difference,
            "chart": {"labels": labels, "datasets": datasets},
            "hourly": {"labels": [], "datasets": [], "peak": None},
            "rate": None,
        }

    @api.model
    def _accumulate(self, device, workorder, count, timestamp):
        naive = timestamp.replace(tzinfo=None) if timestamp.tzinfo else timestamp
        run = self.search(
            [("device_id", "=", device.id), ("workorder_id", "=", workorder.id)],
            limit=1,
        )
        if not run:
            return self.create(
                {
                    "device_id": device.id,
                    "workorder_id": workorder.id,
                    "count_start": count,
                    "count_end": count,
                    "date_start": naive,
                }
            )
        if count == 0 and run.count_end > 0:
            run.write(
                {
                    "count_carried": run.bottles,
                    "count_start": count,
                    "count_end": count,
                    "date_end": naive,
                }
            )
            return run
        if count < run.count_end:
            run.date_end = naive
            return run
        run.write({"count_end": count, "date_end": naive})
        return run

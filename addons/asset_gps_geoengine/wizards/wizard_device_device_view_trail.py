from odoo import api, fields, models
from odoo.fields import Domain


class WizardDeviceDeviceViewTrail(models.TransientModel):
    _inherit = "wizard.device.device.view.trail"

    selection_mode = fields.Selection(
        selection_add=[
            ("asset", "By Asset/Vehicle"),
            ("operator", "By Operator/Driver"),
            ("device",),
        ],
        default="asset",
        ondelete={"asset": "set default", "operator": "set default"},
    )
    asset_ids = fields.Many2many(
        comodel_name="resource.asset",
        relation="gps_trail_wizard_asset_rel",
        column1="wizard_id",
        column2="asset_id",
        domain="[('resource_id.gps_binding_ids', '!=', False)]",
        context={"active_test": False},
        help="Select assets/vehicles with GPS tracking devices",
    )
    operator_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="gps_trail_wizard_operator_rel",
        column1="wizard_id",
        column2="employee_id",
        help="Select operators/drivers to view their assigned vehicle trails",
    )

    def _tracking_periods(self):
        self.check_singleton()
        if self.selection_mode == "operator":
            self.operator_ids.check_access("read")
            resources = (
                self.env["resource.asset"]
                .with_context(active_test=False)
                .search(
                    [
                        (
                            "resource_id",
                            "in",
                            self.env["resource.gps.binding"]._tracked_resource_ids(),
                        )
                    ]
                )
                .resource_id
            )
            periods = self.env["resource.gps.binding"]._custody_periods(
                resources,
                roles=("operator",),
                assignees=self.operator_ids.resource_id,
                date_start=self.date_from,
                date_end=self.date_to,
            )
            return [
                (period.device_id, period.date_start, period.date_end)
                for period in periods
            ]
        if self.selection_mode != "asset":
            return []
        self.asset_ids.check_access("read")
        resources = self.asset_ids.resource_id
        domain = [("resource_id", "in", resources.ids)]
        if self.date_to:
            domain.extend(
                ["|", ("date_start", "=", False), ("date_start", "<=", self.date_to)]
            )
        if self.date_from:
            domain.extend(
                ["|", ("date_end", "=", False), ("date_end", ">", self.date_from)]
            )
        bindings = self.env["resource.gps.binding"].search(domain)
        return [
            (binding.device_id.id, binding.date_start, binding.date_end)
            for binding in bindings
        ]

    @api.depends("selection_mode", "asset_ids", "operator_ids", "date_from", "date_to")
    def _compute_resolved_devices(self):
        by_device = self.filtered(lambda wizard: wizard.selection_mode == "device")
        super(WizardDeviceDeviceViewTrail, by_device)._compute_resolved_devices()
        for wizard in self - by_device:
            wizard.resolved_device_ids = self.env["device.device"].browse(
                sorted(
                    {
                        device_id
                        for device_id, _start, _end in wizard._tracking_periods()
                    }
                )
            )

    def _gps_trail_domain(self):
        domain = super()._gps_trail_domain()
        if self.selection_mode == "device":
            return domain
        periods = []
        for device_id, start, end in self._tracking_periods():
            period = Domain("device_id", "=", device_id)
            if start:
                period &= Domain("timestamp", ">=", start)
            if end:
                period &= Domain("timestamp", "<", end)
            periods.append(period)
        return domain & Domain.OR(periods)

    def _prepare_trail_logs(self, logs, source_mapping):
        logs, source_mapping = super()._prepare_trail_logs(logs, source_mapping)
        assets = (
            self.env["resource.asset"]
            .with_context(active_test=False)
            .search(
                [
                    (
                        "resource_id",
                        "in",
                        sorted(
                            {
                                log["resource_id"]
                                for log in logs
                                if log.get("resource_id")
                            }
                        ),
                    )
                ]
            )
        )
        by_resource = {asset.resource_id.id: asset for asset in assets}
        assignments = self.env["resource.assignment"].search(
            [
                ("resource_id", "in", assets.resource_id.ids),
                ("custody_role", "=", "operator"),
                ("date_start", "<=", self.date_to),
                "|",
                ("date_end", "=", False),
                ("date_end", ">", self.date_from),
            ],
            order="date_start desc, id desc",
        )
        holders = assignments.grouped("resource_id")
        employees = {
            employee.resource_id: employee
            for employee in self.env["hr.employee"]
            .with_context(active_test=False)
            .search([("resource_id", "in", assignments.assignee_id.ids)])
        }
        mapping = {}
        for log in logs:
            asset = by_resource.get(log.get("resource_id"), assets.browse())
            at = log["timestamp"]
            holder = holders.get(asset.resource_id, assignments.browse()).filtered(
                lambda assignment, at=at: (
                    assignment.date_start <= at
                    and (not assignment.date_end or assignment.date_end > at)
                )
            )[:1]
            operator = employees.get(holder.assignee_id)
            key = (log["device_id"], log.get("binding_id"), holder.id)
            log["source_key"] = key
            if key not in mapping:
                mapping[key] = {
                    **source_mapping.get(log["device_id"], {}),
                    "asset_id": asset.id,
                    "asset_name": asset.display_name if asset else False,
                    "license_plate": asset.license_plate if asset else False,
                    "operator_id": operator.id if operator else False,
                    "operator_name": operator.name if operator else False,
                }
        return logs, mapping

    @api.depends("asset_ids", "operator_ids")
    def _compute_selection_summary(self) -> None:
        by_device = self.filtered(lambda w: w.selection_mode == "device")
        super(WizardDeviceDeviceViewTrail, by_device)._compute_selection_summary()

        for wizard in self - by_device:
            if wizard.selection_mode == "asset":
                count = len(wizard.asset_ids)
                if count == 0:
                    wizard.selection_summary = self.env._("No assets selected")
                elif count == 1:
                    asset = wizard.asset_ids[0]
                    plate = f" ({asset.license_plate})" if asset.license_plate else ""
                    wizard.selection_summary = f"{asset.name}{plate}"
                else:
                    wizard.selection_summary = self.env._("%d assets selected") % count
            else:
                count = len(wizard.operator_ids)
                if count == 0:
                    wizard.selection_summary = self.env._("No operators selected")
                elif count == 1:
                    wizard.selection_summary = wizard.operator_ids[0].name
                else:
                    wizard.selection_summary = (
                        self.env._("%d operators selected") % count
                    )

    @api.onchange("selection_mode")
    def _onchange_selection_mode(self) -> None:
        super()._onchange_selection_mode()
        self.asset_ids = False
        self.operator_ids = False

    def _empty_selection_message(self):
        self.check_singleton()
        if self.selection_mode == "asset":
            return self.env._("Please select at least one asset with a GPS device")
        if self.selection_mode == "operator":
            return self.env._(
                "Please select at least one operator with an assigned vehicle"
            )
        return super()._empty_selection_message()

    def _trail_source_extras(self, device):
        extras = super()._trail_source_extras(device)
        asset = device.asset_id
        operator = asset.operator_employee_id
        extras.update(
            {
                "asset_id": asset.id if asset else False,
                "asset_name": asset.name if asset else False,
                "license_plate": asset.license_plate or False if asset else False,
                "operator_id": operator.id if operator else False,
                "operator_name": operator.name if operator else False,
            }
        )
        return extras

    def _trail_result_vals(self, source_info):
        vals = super()._trail_result_vals(source_info)
        vals.update(
            {
                "asset_id": source_info.get("asset_id"),
                "operator_id": source_info.get("operator_id"),
            }
        )
        return vals

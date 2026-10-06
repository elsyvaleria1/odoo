from odoo import api, fields, models


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    plc_run_ids = fields.One2many(
        comodel_name="device.machine.workorder",
        inverse_name="workorder_id",
        string="PLC Runs",
    )
    plc_run_count = fields.Count(count_of="plc_run_ids")
    plc_bottle_count = fields.Integer(
        compute="_compute_plc_bottle_count",
        store=True,
        help="Units counted by the PLC during this work order. Independent of "
        "the manually reported quantity; use it for verification.",
    )
    plc_qty_variance = fields.Float(
        compute="_compute_plc_qty_variance",
        help="Manually reported quantity minus the PLC bottle count.",
    )

    @api.depends("plc_run_ids.bottles")
    def _compute_plc_bottle_count(self) -> None:
        for workorder in self:
            workorder.plc_bottle_count = sum(workorder.plc_run_ids.mapped("bottles"))

    @api.depends("qty_produced", "plc_bottle_count")
    def _compute_plc_qty_variance(self) -> None:
        for workorder in self:
            workorder.plc_qty_variance = (
                workorder.qty_produced - workorder.plc_bottle_count
            )

    def action_view_plc_runs(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.client",
            "tag": "plc_dashboard",
            "name": self.env._("Bottles Filled and Labeled"),
            "context": {"plc_workorder_id": self.id},
        }

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # A kit operation's history is frozen when its work order finishes. Work
    # orders finished before that are frozen now, at the kit's current ratio:
    # the one their learned cycle was already read through, so nothing that was
    # learned changes, and later edits to the kit stop rewriting it.
    workorders = env["mrp.workorder"].search(
        [
            ("state", "=", "done"),
            ("qty_produced", ">", 0),
            ("operation_demand_qty", "=", 0),
            ("operation_id.bom_id", "!=", False),
        ]
    )
    for workorder in workorders.filtered(
        lambda wo: wo.operation_id.bom_id != wo.production_bom_id
    ):
        if vals := workorder._prepare_operation_demand_vals(workorder.qty_produced):
            workorder.write(vals)

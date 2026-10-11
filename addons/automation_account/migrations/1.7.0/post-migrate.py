from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["ir.actions.server"].search(
        [("workflow_source_step_id", "!=", False)]
    )._compute_step_references()

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    # automation computed every step's stored references before this module's
    # override was loaded, so a step naming its source step lacks that key.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["ir.actions.server"].search(
        [("workflow_source_step_id", "!=", False)]
    )._compute_step_references()

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Reconcile only work awaiting execution; running and completed bookings
    # retain their recorded identity. Shared constraints reject unsafe moves.
    env["mrp.workorder"].search(
        [
            ("state", "in", ("ready", "blocked")),
            ("date_start", "!=", False),
            ("date_end", "!=", False),
        ]
    )._sync_reservations()

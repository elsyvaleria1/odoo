from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # a channel's principal now runs without su, so it belongs to the company
    # of each enrollment it runs for
    env["device.enrollment"].search([("state", "!=", "revoked")])._place_service_user()

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["device.enrollment"].search([("state", "!=", "revoked")])._place_service_user()

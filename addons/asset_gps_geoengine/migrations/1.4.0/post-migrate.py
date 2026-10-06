from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if version:
        env = api.Environment(cr, SUPERUSER_ID, {})
        env["device.gps.stop"]._mark_dates_stale()

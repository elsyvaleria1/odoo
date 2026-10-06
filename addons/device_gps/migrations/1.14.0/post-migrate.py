from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["resource.gps.binding"]._bootstrap_legacy()
    env["device.data.log.gps.report"]._rolling_mark_stale()

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # a device's receiver is to run without su, so it belongs to the company of
    # each device it receives for
    env["device.device"].search([])._place_receiver()

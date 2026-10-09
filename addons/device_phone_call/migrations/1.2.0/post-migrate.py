from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # a phone system's receiver files calls without su under the company of
    # each line it carries, so it belongs to every one of them
    env["device.device"].search([])._place_receiver()

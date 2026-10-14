from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    principal = env.ref("runner.user_runner", raise_if_not_found=False)
    if principal:
        principal.active = True
    env["runner.machine"].search([])._place_service_user()

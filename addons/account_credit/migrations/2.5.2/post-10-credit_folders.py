from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["credit.config"].with_context(active_test=False).search(
        [("credit_folder_id", "=", False)]
    )._provision_credit_folder()

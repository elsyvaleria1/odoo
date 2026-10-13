from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    account_return = env["account.return"]
    account_return.search(
        account_return._open_audit_domain()
    )._create_missing_audit_account_statuses()

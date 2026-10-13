from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    AccountStatus = env["account.audit.account.status"]
    duplicate_ids = [
        status_id
        for _audit, _account, status_ids in AccountStatus._read_group(
            [],
            ["audit_id", "account_id"],
            ["id:array_agg"],
            having=[("__count", ">", 1)],
        )
        for status_id in status_ids
    ]
    AccountStatus.browse(duplicate_ids)._collapse_to_most_urgent(
        lambda status: (status.audit_id, status.account_id)
    )

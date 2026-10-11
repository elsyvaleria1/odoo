from odoo.tools import module_data

RENAMED_FIELDS = (
    ("account.payment", "destination_account_id", "counterpart_account_id"),
    ("account.payment", "outstanding_account_id", "liquidity_account_id"),
)


def migrate(cr, version):
    if not version:
        return
    for model, old, new in RENAMED_FIELDS:
        module_data.rename_field(cr, model, old, new)

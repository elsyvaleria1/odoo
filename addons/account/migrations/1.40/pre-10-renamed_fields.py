from odoo.tools import module_data

RENAMED_FIELDS = (
    ("account.move", "auto_post_failed", "is_auto_post_failed"),
    ("account.move", "invoice_currency_rate_manual", "is_invoice_currency_rate_manual"),
)


def migrate(cr, version):
    if not version:
        return
    for model, old, new in RENAMED_FIELDS:
        module_data.rename_field(cr, model, old, new)

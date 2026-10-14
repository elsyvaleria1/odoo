from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env["account.move.line"].search(
        [
            ("parent_state", "=", "draft"),
            ("display_type", "=", "product"),
            ("is_imported", "=", False),
            ("tax_ids_auto_key", "=", False),
        ]
    )
    for line in lines:
        line.tax_ids_auto_key = line._tax_key(line._auto_taxes())

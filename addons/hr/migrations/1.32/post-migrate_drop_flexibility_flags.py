from odoo.db import schema


def migrate(cr, version):
    if not version:
        return
    schema.drop_columns(cr, "hr_version", ["is_flexible", "is_fully_flexible"])

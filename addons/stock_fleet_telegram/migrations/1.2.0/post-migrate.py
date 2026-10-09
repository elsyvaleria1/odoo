from odoo.db import schema


def migrate(cr, version):
    """A slip's customer and company are its delivery order's, read through
    the join: the copies the ORM leaves behind are dropped."""
    if not version:
        return
    schema.drop_columns(cr, "telegram_delivery_slip", ["partner_id", "company_id"])

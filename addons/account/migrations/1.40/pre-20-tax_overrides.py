def migrate(cr, version):
    if not version:
        return
    cr.execute(
        "ALTER TABLE account_move ADD COLUMN IF NOT EXISTS is_tax_overridden boolean"
    )

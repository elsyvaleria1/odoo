def migrate(cr, version):
    if not version:
        return
    # no entry holds a manual tax amount before 1.40: creating the column here
    # spares the registry a recompute of the flag over every journal entry
    cr.execute(
        "ALTER TABLE account_move ADD COLUMN IF NOT EXISTS is_tax_overridden boolean"
    )

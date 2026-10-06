from odoo.db import schema


def migrate(cr, version):
    if not version:
        return
    # The version's schedule says whether it is flexible; these restated it.
    # Cascading: an older planning report view reads them, and its init()
    # rebuilds it without them in the same upgrade.
    schema.drop_columns(cr, "hr_version", ["is_flexible", "is_fully_flexible"])

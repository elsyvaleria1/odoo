from odoo.db.schema import get_table_columns, table_exists
from odoo.tools import SQL

LEGACY = "resource_asset_legacy"


def migrate(cr, version):
    if not version or not table_exists(cr, LEGACY):
        return
    # a column no module reconciled still holds what the asset knew
    for column in get_table_columns(cr, LEGACY):
        if column == "id":
            continue
        cr.execute(
            SQL(
                "SELECT count(*) FROM %s WHERE %s IS NOT NULL",
                SQL.identifier(LEGACY),
                SQL.identifier(column),
            )
        )
        [[count]] = cr.fetchall()
        if count:
            raise ValueError(
                f"{LEGACY}.{column} holds {count} value(s) no module took onto the "
                "resource; nothing was dropped"
            )
    cr.execute(SQL("DROP TABLE %s", SQL.identifier(LEGACY)))

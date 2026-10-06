from odoo.db.schema import table_exists
from odoo.tools import SQL

TO_YEAR = "substring(model_year from '[0-9]{4}')::integer"


def _text_model_year_tables(cr):
    cr.execute(
        """
        SELECT table_name FROM information_schema.columns
         WHERE column_name = 'model_year' AND data_type <> 'integer'
           AND table_name LIKE 'resource_asset%'
        """
    )
    return [row[0] for row in cr.fetchall()]


def migrate(cr, version):
    if not version or not table_exists(cr, "resource_asset"):
        return
    # a model year was free text; the four digits it holds, when it holds them,
    # are the year. The root's change reaches the subtypes that inherit its
    # column; one that declares its own is changed after.
    tables = _text_model_year_tables(cr)
    if "resource_asset" in tables:
        cr.execute(
            SQL(
                "ALTER TABLE resource_asset ALTER COLUMN model_year TYPE integer USING %s",
                SQL(TO_YEAR),
            )
        )
    for table in _text_model_year_tables(cr):
        cr.execute(
            SQL(
                "ALTER TABLE %s ALTER COLUMN model_year TYPE integer USING %s",
                SQL.identifier(table),
                SQL(TO_YEAR),
            )
        )

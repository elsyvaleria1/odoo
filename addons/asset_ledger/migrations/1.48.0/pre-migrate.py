from odoo.db.schema import column_exists


def migrate(cr, version):
    if not version or not column_exists(cr, "product_trace", "model_year"):
        return
    cr.execute(
        """
        ALTER TABLE product_trace ALTER COLUMN model_year TYPE integer
        USING substring(model_year from '[0-9]{4}')::integer
        """
    )

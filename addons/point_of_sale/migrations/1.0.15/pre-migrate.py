from odoo.db import schema


def migrate(cr, version):
    column = schema.get_table_columns(cr, "pos_processed_operation").get("result")
    if not version or not column or column["udt_name"] != "jsonb":
        return
    schema.convert_column(cr, "pos_processed_operation", "result", "text")

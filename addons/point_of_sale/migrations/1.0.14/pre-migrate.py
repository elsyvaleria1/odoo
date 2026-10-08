from odoo.db import schema


def migrate(cr, version):
    if not version or schema.column_exists(
        cr, "pos_order_line", "combo_qty_per_parent"
    ):
        return
    # Filled here in one statement instead of by the ORM's per-record compute
    # over every order line; a child of a combo now at zero keeps no share.
    schema.create_column(cr, "pos_order_line", "combo_qty_per_parent", "float8")
    cr.execute(
        """
        UPDATE pos_order_line child
           SET combo_qty_per_parent = child.qty / parent.qty
          FROM pos_order_line parent
         WHERE child.combo_parent_id = parent.id
           AND parent.qty != 0
        """
    )

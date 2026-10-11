from . import controllers
from . import models
from . import wizards
from . import reports
from odoo.db.schema import column_exists


def _pre_init_rental(env) -> None:
    if not column_exists(env.cr, "sale_order", "rental_status"):
        env.cr.execute("""
            ALTER TABLE "sale_order"
            ADD COLUMN "rental_start_date" timestamp,
            ADD COLUMN "rental_return_date" timestamp,
            ADD COLUMN "rental_status" VARCHAR,
            ADD COLUMN "next_action_date" timestamp
        """)
        env.cr.execute("""
            ALTER TABLE "sale_order_line"
            ADD COLUMN "reservation_begin" timestamp
        """)

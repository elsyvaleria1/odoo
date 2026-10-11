from odoo.tools import SQL


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        SQL(
            "UPDATE approval_category SET escalate_overdue = TRUE "
            "WHERE escalate_overdue IS NOT TRUE"
        )
    )

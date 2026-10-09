from odoo.tools import SQL


def migrate(cr, version):
    # escalate_overdue used to choose only whom an overdue request escalated to,
    # never whether it did; it now decides whether, so every category escalates
    # as it did before the upgrade until someone turns it off
    if not version:
        return
    cr.execute(
        SQL(
            "UPDATE approval_category SET escalate_overdue = TRUE "
            "WHERE escalate_overdue IS NOT TRUE"
        )
    )

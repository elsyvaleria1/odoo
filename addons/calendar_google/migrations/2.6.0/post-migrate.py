from odoo.tools import SQL


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        SQL(
            "DROP TABLE IF EXISTS %s",
            SQL.identifier("wizard_res_users_reset_google_calendar"),
        )
    )

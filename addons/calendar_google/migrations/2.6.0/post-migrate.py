from odoo.tools import SQL


def migrate(cr, version):
    if not version:
        return
    # the reset is calendar_sync's wizard now; nothing defines this one, so
    # nothing else would drop its table
    cr.execute(
        SQL(
            "DROP TABLE IF EXISTS %s",
            SQL.identifier("wizard_res_users_reset_google_calendar"),
        )
    )

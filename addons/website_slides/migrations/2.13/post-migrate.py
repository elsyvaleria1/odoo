from odoo.tools import SQL


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        SQL(
            "UPDATE slide_channel_partner SET date_completed = write_date "
            "WHERE member_status = 'completed' AND date_completed IS NULL"
        )
    )

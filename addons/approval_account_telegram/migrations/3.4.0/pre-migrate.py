from odoo.db import schema
from odoo.tools import SQL


def migrate(cr, version):
    # the category a bot filed /pago and /especie requests in becomes the one
    # its company files them in, before the bot's columns are dropped
    if not version:
        return
    if not schema.column_exists(cr, "approval_category", "telegram_intake"):
        schema.create_column(cr, "approval_category", "telegram_intake", "varchar")
    for intake, column in (
        ("payment", "payment_approval_category_id"),
        ("especie", "especie_approval_category_id"),
    ):
        if not schema.column_exists(cr, "telegram_bot", column):
            continue
        # one category per company and command: the first bot's wins
        cr.execute(
            SQL(
                """
                UPDATE approval_category AS category
                   SET telegram_intake = %s
                  FROM (
                        SELECT DISTINCT ON (COALESCE(c.company_id, 0)) c.id
                          FROM telegram_bot AS bot
                          JOIN approval_category AS c ON c.id = %s
                         WHERE c.telegram_intake IS NULL
                      ORDER BY COALESCE(c.company_id, 0), bot.id
                       ) AS chosen
                 WHERE category.id = chosen.id
                """,
                intake,
                SQL.identifier("bot", column),
            )
        )

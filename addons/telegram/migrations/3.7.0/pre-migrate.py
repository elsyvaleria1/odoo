from odoo.db import schema


def migrate(cr, version):
    if not version or schema.column_exists(cr, "telegram_bot", "company_id"):
        return
    schema.create_column(cr, "telegram_bot", "company_id", "int4")
    cr.execute(
        """
        UPDATE telegram_bot AS bot
           SET company_id = COALESCE(
                   (SELECT u.company_id FROM res_users AS u WHERE u.id = bot.create_uid),
                   (SELECT MIN(c.id) FROM res_company AS c)
               )
        """
    )
    cr.execute(
        """
        UPDATE integration_receiver AS receiver
           SET company_id = bot.company_id
          FROM telegram_bot AS bot
         WHERE receiver.res_model = 'telegram.bot'
           AND receiver.res_id = bot.id
        """
    )

from odoo.db import schema


def migrate(cr, version):
    if not version or not schema.column_exists(
        cr, "telegram_bot", "statement_company_id"
    ):
        return
    cr.execute(
        """
        UPDATE telegram_bot
           SET company_id = statement_company_id
         WHERE statement_company_id IS NOT NULL
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

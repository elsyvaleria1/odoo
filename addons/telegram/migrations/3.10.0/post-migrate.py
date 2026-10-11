def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        INSERT INTO telegram_bot_res_company_rel (telegram_bot_id, res_company_id)
        SELECT id, company_id FROM telegram_bot
        ON CONFLICT DO NOTHING
        """
    )

from odoo.db.schema import column_exists


def migrate(cr, version):
    if not version or not column_exists(cr, "resource_config", "resource_calendar_id"):
        return
    cr.execute(
        """
        UPDATE res_partner partner
           SET tz = calendar.tz
          FROM res_company company
          JOIN resource_config config ON config.company_id = company.id
          JOIN resource_calendar calendar ON calendar.id = config.resource_calendar_id
         WHERE partner.id = company.partner_id
           AND COALESCE(partner.tz, '') = ''
           AND calendar.tz IS NOT NULL
        """
    )

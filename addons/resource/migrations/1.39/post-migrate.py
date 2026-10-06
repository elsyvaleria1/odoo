from odoo.db.schema import column_exists


def migrate(cr, version):
    if not version or not column_exists(cr, "res_partner", "nationality_id"):
        return
    # a person held one nationality; it becomes the first of their rows
    cr.execute(
        """
        INSERT INTO resource_nationality
               (partner_id, country_id, sequence,
                create_uid, write_uid, create_date, write_date)
        SELECT partner.id, partner.nationality_id, 10,
               1, 1, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
          FROM res_partner partner
         WHERE partner.nationality_id IS NOT NULL
           AND NOT EXISTS (
                SELECT 1 FROM resource_nationality held
                 WHERE held.partner_id = partner.id
                   AND held.country_id = partner.nationality_id
           )
        """
    )

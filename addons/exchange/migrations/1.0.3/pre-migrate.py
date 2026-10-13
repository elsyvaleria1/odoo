from odoo.db import schema


def migrate(cr, version):
    if not version or not schema.table_exists(cr, "exchange_transmission_dispatch"):
        return
    cr.execute(
        """
        ALTER TABLE exchange_transmission_dispatch
        DROP CONSTRAINT IF EXISTS exchange_transmission_dispatch_transmission_id_fkey
        """
    )
    if schema.column_exists(cr, "exchange_transmission_dispatch", "company_id"):
        return
    cr.execute("ALTER TABLE exchange_transmission_dispatch ADD COLUMN company_id int4")
    cr.execute(
        """
        UPDATE exchange_transmission_dispatch dispatch
           SET company_id = transmission.company_id
          FROM exchange_transmission transmission
         WHERE transmission.id = dispatch.transmission_id
        """
    )

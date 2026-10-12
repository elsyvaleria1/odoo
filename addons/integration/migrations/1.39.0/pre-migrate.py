from odoo.tools import SQL


def migrate(cr, version):
    # the unique index over (channel_id, event_id_external) became one that
    # leaves failed rows out, so a sender may redeliver an event whose request
    # failed; the ORM does not drop an index a model stops declaring, and the
    # old one kept refusing that redelivery as a duplicate
    if not version:
        return
    cr.execute(SQL("DROP INDEX IF EXISTS integration_exchange_event_external_unique"))

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    api.Environment(cr, SUPERUSER_ID, {})[
        "document.document"
    ]._rekey_thumbnail_sources()

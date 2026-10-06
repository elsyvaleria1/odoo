from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    # 1.27 left a file a storage provider holds to the browser: the server
    # renders those too now, so their source checksum is written and they queue
    api.Environment(cr, SUPERUSER_ID, {})[
        "document.document"
    ]._rekey_thumbnail_sources()

from odoo import SUPERUSER_ID, api

from odoo.addons.calendar_sync.migration import pend_links


def migrate(cr, version):
    if not version:
        return
    pend_links(api.Environment(cr, SUPERUSER_ID, {}), "microsoft", "need_sync_m")

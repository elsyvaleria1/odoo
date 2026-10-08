from odoo.addons.calendar_sync.migration import settle_duplicate_links


def migrate(cr, version):
    if not version:
        return
    settle_duplicate_links(cr)

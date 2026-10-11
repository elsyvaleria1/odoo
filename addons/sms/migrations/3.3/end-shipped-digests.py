from odoo import SUPERUSER_ID, api

from odoo.addons.base.models.mixin_template_trust import migrate_shipped_digests


def migrate(cr, version):
    if not version:
        return
    migrate_shipped_digests(api.Environment(cr, SUPERUSER_ID, {}), "sms.template")

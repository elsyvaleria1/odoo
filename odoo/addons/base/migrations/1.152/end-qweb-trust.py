from odoo import SUPERUSER_ID, api

from odoo.addons.base.models.mixin_template_trust import migrate_shipped_digests


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_shipped_digests(env, "ir.ui.view")
